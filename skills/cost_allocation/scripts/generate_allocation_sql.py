"""
Generate Allocation SQL Script

This script generates SQL queries for cost allocation based on the provided parameters.
It implements the business logic for calculating allocated costs across different
functions and business lines.

Usage:
    python generate_allocation_sql.py --years FY25 --scenarios Actual --function "IT Allocation" --party_field "t7.[BL]" --party_value "'CT'"
"""

import sys
import argparse
from typing import List, Optional

# SQL Template for Allocation Calculation
# Uses CTEs for readability and performance
ALLOC_TEMPLATE = """
WITH monthly_alloc AS (
    SELECT
        cdb.year AS "Year",
        -- Calculate Base Cost (handling NULLs)
        COALESCE(SUM(CAST(cdb.amount AS FLOAT)), 0) AS "Base_Month_Cost",
        
        -- Calculate Allocated Cost: Cost * Rate
        -- Handles numeric RateNo directly
        COALESCE(SUM(CAST(cdb.amount AS FLOAT) * COALESCE(t7.rate_no, 0)), 0) AS "Allocated_Month_Cost",
            
        {party_field} AS "Allocated_Party"
    FROM SSME_FI_InsightBot_CostDataBase cdb
    LEFT JOIN SSME_FI_InsightBot_Rate t7
        ON cdb.year = t7.year
        AND cdb.scenario = t7.scenario
        AND cdb.key = t7.key
        AND cdb.month = t7.month
    WHERE {year_filter}
      AND {scenario_filter}
      AND cdb.function = {function_literal}
      AND {party_filter}
    GROUP BY cdb.year, {party_field}
),
yearly_agg AS (
    SELECT
        "Year",
        "Allocated_Party",
        SUM("Allocated_Month_Cost") AS "Year_Allocated_Cost"
    FROM monthly_alloc
    GROUP BY "Year", "Allocated_Party"
),
compare AS (
    SELECT
        "Allocated_Party",
        "Year",
        "Year_Allocated_Cost",
        -- Calculate Previous Year's Cost for Comparison
        LAG("Year_Allocated_Cost") OVER (PARTITION BY "Allocated_Party" ORDER BY "Year") AS "Prev_Allocated_Cost"
    FROM yearly_agg
)
SELECT
    "Allocated_Party",
    "Year",
    "Year_Allocated_Cost",
    
    -- Calculate Difference
    CASE 
        WHEN "Prev_Allocated_Cost" IS NULL THEN NULL 
        ELSE "Year_Allocated_Cost" - "Prev_Allocated_Cost" 
    END AS "Allocated_Cost_Diff",
    
    -- Calculate Growth Rate (%)
    CASE 
        WHEN "Prev_Allocated_Cost" IS NULL OR "Prev_Allocated_Cost" = 0 THEN 0
        ELSE ROUND(CAST((("Year_Allocated_Cost" / "Prev_Allocated_Cost") - 1) * 100 AS NUMERIC), 2) 
    END AS "Allocated_Cost_Diff_Rate(%)"
FROM compare
ORDER BY "Allocated_Party", "Year" DESC;
"""


def _quote_literal(s: str) -> str:
    """Safely quote a string literal for SQL."""
    if not s:
        return "''"
    return "'{}'".format(s.replace("'", "''"))


def _build_or_list(items: List[str], field_name: str) -> str:
    """Build a SQL OR clause for a list of values."""
    if not items:
        return "1=1"

    lits = [_quote_literal(i) for i in items]

    if len(lits) == 1:
        return f"{field_name} = {lits[0]}"

    return f"({field_name} IN ({', '.join(lits)}))"


def generate_alloc_sql(
    years: List[str],
    scenarios: List[str],
    function_name: str,
    party_field: str,
    party_value: str,
) -> str:
    """
    Generate the SQL query for cost allocation.

    Args:
        years: List of fiscal years to filter (e.g., ['FY25'])
        scenarios: List of scenarios (e.g., ['Actual'])
        function_name: Function name (e.g., 'IT Allocation')
        party_field: The field representing the allocated party (e.g., 't7.[BL]')
        party_value: The value for the party field (e.g., "'CT'")

    Returns:
        Formatted SQL query string.
    """
    # Validation
    if not years:
        raise ValueError("At least one year must be provided")
    if not scenarios:
        raise ValueError("At least one scenario must be provided")
    if not function_name:
        raise ValueError("Function name is required")

    year_filter = _build_or_list(years, "cdb.year")
    scenario_filter = _build_or_list(scenarios, "cdb.scenario")
    function_literal = _quote_literal(function_name)
    party_filter = f"{party_field} = {party_value}"

    return ALLOC_TEMPLATE.format(
        party_field=party_field,
        year_filter=year_filter,
        scenario_filter=scenario_filter,
        function_literal=function_literal,
        party_filter=party_filter,
    ).strip()


def main():
    parser = argparse.ArgumentParser(description="Generate Allocation SQL")
    parser.add_argument(
        "--years", nargs="+", required=True, help="List of years (e.g. FY24 FY25)"
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        required=True,
        help="List of scenarios (e.g. Actual Budget)",
    )
    parser.add_argument("--function", required=True, help="Function name")
    parser.add_argument(
        "--party_field", required=True, help="Party field name (e.g. t7.[BL])"
    )
    parser.add_argument("--party_value", required=True, help="Party value")

    args = parser.parse_args()

    try:
        sql = generate_alloc_sql(
            years=args.years,
            scenarios=args.scenarios,
            function_name=args.function,
            party_field=args.party_field,
            party_value=args.party_value,
        )
        print(sql)
    except Exception as e:
        print(f"Error generating SQL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
