# Databricks notebook source
# DBTITLE 1,Install openpyxl
# MAGIC %pip install openpyxl

# COMMAND ----------

# MAGIC %restart_python

# COMMAND ----------

import pandas as pd
import numpy as np
import re
from pathlib import Path

SOURCE_FILE = Path("/Volumes/workspace/raw/rawvolume/rawdata/CustomerExtract.csv")
SPEC_FILE = Path("/Volumes/workspace/raw/rawvolume/rawdata/TransformationSpec.xlsx")
OUTPUT_FILE = Path("/Volumes/workspace/raw/rawvolume/rawdata/CustomerLoad.csv")

customer_df = pd.read_csv(SOURCE_FILE)
spec_df = pd.read_excel(SPEC_FILE, sheet_name="CustomerSpec")

# COMMAND ----------

print("Rows:", customer_df.shape[0])
print("Columns:", customer_df.shape[1])


# COMMAND ----------

customer_df.head()

# COMMAND ----------

customer_df.info()

# COMMAND ----------

customer_df.describe(include="all").T

# COMMAND ----------

# MAGIC %md
# MAGIC **Null / completeness profiling** 
# MAGIC
# MAGIC Clean DQ table

# COMMAND ----------

profile = pd.DataFrame({
    "Column": customer_df.columns,
    "Data_Type": customer_df.dtypes.astype(str).values,
    "Record_Count": len(customer_df),
    "Non_Null_Count": customer_df.notna().sum().values,
    "Null_Count": customer_df.isna().sum().values
})

profile["Null_%"] = (
    profile["Null_Count"] / profile["Record_Count"] * 100
).round(2)

profile

# COMMAND ----------

# MAGIC %md
# MAGIC **Check duplicate Customer IDs**
# MAGIC
# MAGIC KUNNR is the customer account number and should be unique for the source records.

# COMMAND ----------

duplicate_kunnr = customer_df[
    customer_df["KUNNR"].duplicated(keep=False)
]

print("Duplicate KUNNR records:", len(duplicate_kunnr))

# COMMAND ----------

customer_df["KUNNR"].isna().sum()

# COMMAND ----------

print(customer_df["KUNNR"])

# COMMAND ----------

# MAGIC %md
# MAGIC **pecification-based DQ check**
# MAGIC
# MAGIC Are there any fields in the extract that are populated with data that are not flagged in the spec as "Field Utilized in LEGACY System"?
# MAGIC
# MAGIC So we compare:
# MAGIC
# MAGIC CustomerExtract columns
# MAGIC              VS
# MAGIC Spec → Field Utilized in LEGACY System = Y

# COMMAND ----------

legacy_fields = set(
    spec_df.loc[
        spec_df["Field Utilized in LEGACY System"] == "Y",
        "SAP FIELD"
    ]
)

source_fields = set(customer_df.columns)

unexpected_fields = source_fields - legacy_fields

# COMMAND ----------

# MAGIC %md
# MAGIC We only care about unexpected fields that actually contain data.

# COMMAND ----------

populated_unexpected_fields = [
    col for col in unexpected_fields
    if customer_df[col].notna().any()
]

# COMMAND ----------

# MAGIC %md
# MAGIC **Required field validation**
# MAGIC
# MAGIC We should identify required fields from the specification.

# COMMAND ----------

required_fields = spec_df[
    spec_df["NEW REQ"].astype(str).str.contains("REQ", na=False)
]["SAP FIELD"].dropna().tolist()

# COMMAND ----------

# For fields available in the source:

required_source_fields = [
    c for c in required_fields
    if c in customer_df.columns
]


required_nulls = customer_df[required_source_fields].isna().sum()

required_nulls[required_nulls > 0]

# COMMAND ----------

# MAGIC %md
# MAGIC **Length validation**
# MAGIC
# MAGIC The specification provides maximum lengths.

# COMMAND ----------

def check_length(df, field, max_length):
    if field not in df.columns:
        return 0
    
    return (
        df[field]
        .fillna("")
        .astype(str)
        .str.len()
        .gt(max_length)
        .sum()
    )

# COMMAND ----------

# MAGIC %md
# MAGIC **Data cleansing**
# MAGIC
# MAGIC Now we actually modify the data.
# MAGIC
# MAGIC special characters in the Name 1 field

# COMMAND ----------

def clean_name(value):
    if pd.isna(value):
        return value

    value = str(value).strip()

    value = value.replace('"', '')

    value = re.sub(r"\s+", " ", value)

    return value

# COMMAND ----------

customer_df["NAME1"] = customer_df["NAME1"].apply(clean_name)

# COMMAND ----------

# MAGIC %md
# MAGIC Standardize blank values
# MAGIC
# MAGIC We should also normalize empty strings.

# COMMAND ----------

customer_df = customer_df.replace(r"^\s*$", np.nan, regex=True)

# COMMAND ----------

# MAGIC %md
# MAGIC This is a normal ETL cleansing step.

# COMMAND ----------

for col in customer_df.select_dtypes(include="object").columns:
    customer_df[col] = customer_df[col].str.strip()

# COMMAND ----------

# MAGIC %md
# MAGIC **Transformation layer** actual migration transformation.

# COMMAND ----------

# MAGIC %md
# MAGIC **Create target dataframe**
# MAGIC
# MAGIC Rather than modifying the original 183-column dataframe, I'd create a separate target dataframe.

# COMMAND ----------

target_df = pd.DataFrame()

# COMMAND ----------

target_df["KTOKD"] = customer_df["KTOKD"]
target_df["KUNNR"] = customer_df["KUNNR"]

target_df["BUKRS"] = "G100"
target_df["VKORG"] = "G100"
target_df["VTWEG"] = "20"
target_df["SPART"] = "10"

target_df["LAND1"] = customer_df["LAND1"]
target_df["NAME1"] = customer_df["NAME1"]
target_df["NAME2"] = customer_df["NAME2"]
target_df["ORT01"] = customer_df["ORT01"]
target_df["PSTLZ"] = customer_df["PSTLZ"]
target_df["REGIO"] = customer_df["REGIO"]

# COMMAND ----------

# MAGIC %md
# MAGIC **Important SORTL transformation**
# MAGIC
# MAGIC Sort field will be populated with the first 10 characters from the customer's name.

# COMMAND ----------

# MAGIC %md
# MAGIC This is better than simply copying the source SORTL, because the specification explicitly defines the transformation.

# COMMAND ----------

target_df["SORTL"] = (
    target_df["NAME1"]
    .fillna("")
    .str[:10]
)

# COMMAND ----------

# MAGIC %md
# MAGIC **Language transformation**
# MAGIC
# MAGIC Both Systems use EN
# MAGIC
# MAGIC Even though source contains SPRAS, the transformation rule takes precedence.
# MAGIC
# MAGIC

# COMMAND ----------

target_df["SPRAS"] = "EN"

# COMMAND ----------

# MAGIC %md
# MAGIC ERDAT → DEF by System
# MAGIC ERNAM → DEF by System
# MAGIC
# MAGIC we need to decide how to represent this in the flat file.
# MAGIC
# MAGIC ERDAT and ERNAM are system-defined target fields and therefore are not derived from the legacy extract unless the target loading process requires explicit values.
# MAGIC
# MAGIC If the required output schema expects those columns, we can keep them blank/NULL and clearly document why.

# COMMAND ----------

# MAGIC %md
# MAGIC **Post-transformation DQ**
# MAGIC
# MAGIC After creating target_df, run validation again.
# MAGIC
# MAGIC Record count

# COMMAND ----------

assert len(target_df) == len(customer_df)

# Source records = 100
# Target records = 100

# COMMAND ----------

# MAGIC %md
# MAGIC Duplicate customer IDs

# COMMAND ----------

target_df["KUNNR"].duplicated().sum()

# COMMAND ----------

print(target_df)

# COMMAND ----------

# MAGIC %md
# MAGIC Required fields

# COMMAND ----------

target_df[required_target_fields].isna().sum()

# COMMAND ----------

# MAGIC %md
# MAGIC Constant transformation checks
# MAGIC
# MAGIC This gives very strong traceability.

# COMMAND ----------

assert target_df["BUKRS"].eq("G100").all()
assert target_df["VKORG"].eq("G100").all()
assert target_df["VTWEG"].eq("20").all()
assert target_df["SPART"].eq("10").all()
assert target_df["SPRAS"].eq("EN").all()

# COMMAND ----------

print(target_df)

# COMMAND ----------

# MAGIC %md
# MAGIC **Reconciliation** -  Source and Target record count

# COMMAND ----------

source_record_count = len(customer_df)
target_record_count = len(target_df)

print("Source Record Count :", source_record_count)
print("Target Record Count :", target_record_count)

# COMMAND ----------

# MAGIC %md
# MAGIC **calculate diference**

# COMMAND ----------

record_difference = source_record_count - target_record_count

print("Record Difference   :", record_difference)

if record_difference == 0:
    print("PASS - Source and target record counts match")
else:
    print("FAIL - Record count mismatch detected")

# COMMAND ----------

# MAGIC %md
# MAGIC whether the target contains duplicate customer numbers.

# COMMAND ----------

source_duplicate_count = customer_df["KUNNR"].duplicated().sum()
target_duplicate_count = target_df["KUNNR"].duplicated().sum()

print("Source duplicate KUNNR :", source_duplicate_count)
print("Target duplicate KUNNR :", target_duplicate_count)

# COMMAND ----------

# MAGIC %md
# MAGIC **Load CustomerLoad.csv**

# COMMAND ----------


target_df.to_csv(
    "/Volumes/workspace/raw/rawvolume/rawdata/CustomerLoad.csv",
    index=False
)

# COMMAND ----------

Final_output = pd.read_csv("/Volumes/workspace/raw/rawvolume/rawdata/CustomerLoad.csv")

print("Output file created successfully")
print("Rows:", len(Final_output))
print("Columns:", len(Final_output.columns))

# COMMAND ----------

# MAGIC %md
# MAGIC **- Final output validation**

# COMMAND ----------

print("Source records       :", len(customer_df))
print("Target records       :", len(target_df))
print("Final output records :", len(Final_output))
print("Final output file    :", Final_output)

# COMMAND ----------

assert len(Final_output) == len(target_df)

print("PASS - Output file successfully validated")