# Customer Master Data Migration

## Objective

Transform legacy Customer Master data into the format required
for loading into the new SAP entity.

## Input

CustomerExtract.csv
TransformationSpec.xlsx

## Output

CustomerLoad.csv

## Processing

1. Data loading
2. Data profiling
3. Data quality validation
4. Data cleansing
5. Transformation
6. Post-transformation validation
7. Output generation

## Requirements

Python 3.x
pandas
numpy
openpyxl
jupyter

## Installation

pip install -r requirements.txt

## Execution

jupyter notebook

Open:
notebooks/Customer_Master_Migration.ipynb
