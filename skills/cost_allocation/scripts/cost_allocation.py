"""
Cost Allocation Query Engine

Query cost allocation data from PostgreSQL database.
Supports various query types: cost lookup, allocation calculation, trend analysis.

Usage:
    python cost_allocation.py query --type cost --year FY26 --scenario Budget1 --function HR
    python cost_allocation.py query --type allocation --year FY25 --scenario Actual --function "IT Allocation" --bl CT
    python cost_allocation.py query --type trend --function Procurement --cost-text "Pooling & MPC"
"""

import argparse
import asyncio
import asyncpg
import json
import os
import sys
from decimal import Decimal
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict


# Database Configuration
def get_db_config():
    """Get database configuration from environment or defaults"""
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", 5432)),
        "database": os.getenv("POSTGRES_DB", "cost_allocation"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "123456"),
    }


@dataclass
class QueryResult:
    """Query result container"""

    success: bool
    data: Any
    message: str = ""
    query_type: str = ""


class CostAllocationManager:
    """Manager for cost allocation queries"""

    def __init__(self):
        self.conn = None

    async def connect(self):
        """Connect to database"""
        config = get_db_config()
        self.conn = await asyncpg.connect(**config)
        return self

    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            self.conn = None

    async def query_cost(
        self,
        year: str,
        scenario: str,
        function: str,
        cost_text: Optional[str] = None,
        month: Optional[str] = None,
    ) -> QueryResult:
        """
        Query basic cost information

        Args:
            year: Fiscal year (e.g., FY25, FY26)
            scenario: Budget scenario (Actual, Budget1)
            function: Function name (HR, IT Allocation, etc.)
            cost_text: Optional specific cost text filter
            month: Optional specific month filter (e.g., Oct)
        """
        try:
            query = """
                SELECT 
                    cost_text,
                    key,
                    SUM(amount) as total_cost,
                    COUNT(*) as record_count
                FROM cost_database
                WHERE year = $1 
                AND scenario = $2 
                AND function = $3
            """

            params = [year, scenario, function]

            if cost_text:
                query += " AND cost_text = $4"
                params.append(cost_text)

            if month:
                query += " AND month = $" + str(len(params) + 1)
                params.append(month)

            query += " GROUP BY cost_text, key ORDER BY total_cost DESC"

            rows = await self.conn.fetch(query, *params)

            if not rows:
                return QueryResult(
                    success=False,
                    data=None,
                    message=f"No data found for {function} in {year} {scenario}",
                    query_type="cost",
                )

            total = sum(r["total_cost"] for r in rows)

            result_data = {
                "year": year,
                "scenario": scenario,
                "function": function,
                "cost_text_filter": cost_text,
                "month_filter": month,
                "total_cost": float(total),
                "breakdown": [
                    {
                        "cost_text": r["cost_text"],
                        "key": r["key"],
                        "amount": float(r["total_cost"]),
                        "records": r["record_count"],
                    }
                    for r in rows
                ],
            }

            return QueryResult(
                success=True,
                data=result_data,
                message=f"Found {len(rows)} cost items, total: {total:,.2f}",
                query_type="cost",
            )

        except Exception as e:
            return QueryResult(
                success=False,
                data=None,
                message=f"Query error: {str(e)}",
                query_type="cost",
            )

    async def query_allocation(
        self,
        year: str,
        scenario: str,
        function: str,
        party_type: str,  # 'bl' or 'cc'
        party_value: str,
        cost_text: Optional[str] = None,
        month: Optional[str] = None,
    ) -> QueryResult:
        """
        Calculate allocated cost to a specific party

        Args:
            year: Fiscal year
            scenario: Budget scenario
            function: Function name (must be Allocation type)
            party_type: 'bl' for business line or 'cc' for cost center
            party_value: The party identifier (e.g., 'CT', '413001')
            cost_text: Optional specific cost text filter
            month: Optional specific month filter
        """
        try:
            party_field = "rt.bl" if party_type == "bl" else "rt.cc"

            base_query = """
                SELECT 
                    cd.cost_text,
                    SUM(ABS(cd.amount) * rt.rate_no) as allocated_amount
                FROM cost_database cd
                JOIN rate_table rt ON cd.key = rt.key 
                    AND cd.year = rt.year 
                    AND cd.scenario = rt.scenario 
                    AND cd.month = rt.month
                WHERE cd.year = $1 
                AND cd.scenario = $2 
                AND cd.function = $3
                AND {} = $4
            """.format(
                party_field
            )

            params = [year, scenario, function, party_value]

            if cost_text:
                base_query += " AND cd.cost_text = $" + str(len(params) + 1)
                params.append(cost_text)

            if month:
                base_query += " AND cd.month = $" + str(len(params) + 1)
                params.append(month)

            base_query += " GROUP BY cd.cost_text"

            rows = await self.conn.fetch(base_query, *params)

            if not rows:
                return QueryResult(
                    success=False,
                    data=None,
                    message=f"No allocation data found for {function} to {party_value}",
                    query_type="allocation",
                )

            total_allocated = sum(r["allocated_amount"] for r in rows)

            result_data = {
                "year": year,
                "scenario": scenario,
                "function": function,
                "party_type": party_type,
                "party_value": party_value,
                "cost_text_filter": cost_text,
                "month_filter": month,
                "allocated_cost": float(total_allocated),
                "breakdown": [
                    {
                        "cost_text": r["cost_text"],
                        "amount": float(r["allocated_amount"]),
                    }
                    for r in rows
                ],
            }

            return QueryResult(
                success=True,
                data=result_data,
                message=f"Allocated cost to {party_value}: {total_allocated:,.2f}",
                query_type="allocation",
            )

        except Exception as e:
            return QueryResult(
                success=False,
                data=None,
                message=f"Query error: {str(e)}",
                query_type="allocation",
            )

    async def query_trend(
        self,
        function: str,
        cost_text: Optional[str] = None,
        party_type: Optional[str] = None,
        party_value: Optional[str] = None,
    ) -> QueryResult:
        """
        Query trend analysis (FY25 Actual vs FY26 Budget)

        Args:
            function: Function name
            cost_text: Optional specific cost text
            party_type: Optional 'bl' or 'cc' for allocation
            party_value: Optional party identifier
        """
        try:
            if party_type and party_value:
                # Allocation trend
                party_field = "rt.bl" if party_type == "bl" else "rt.cc"

                fy25 = await self.conn.fetchval(
                    """
                    SELECT SUM(ABS(cd.amount) * rt.rate_no)
                    FROM cost_database cd
                    JOIN rate_table rt ON cd.key = rt.key 
                        AND cd.year = rt.year 
                        AND cd.scenario = rt.scenario 
                        AND cd.month = rt.month
                    WHERE cd.year = 'FY25' 
                    AND cd.scenario = 'Actual' 
                    AND cd.function = $1
                    AND {} = $2
                """.format(
                        party_field
                    ),
                    function,
                    party_value,
                )

                fy26 = await self.conn.fetchval(
                    """
                    SELECT SUM(ABS(cd.amount) * rt.rate_no)
                    FROM cost_database cd
                    JOIN rate_table rt ON cd.key = rt.key 
                        AND cd.year = rt.year 
                        AND cd.scenario = rt.scenario 
                        AND cd.month = rt.month
                    WHERE cd.year = 'FY26' 
                    AND cd.scenario = 'Budget1' 
                    AND cd.function = $1
                    AND {} = $2
                """.format(
                        party_field
                    ),
                    function,
                    party_value,
                )

            else:
                # Basic cost trend
                if cost_text:
                    base_query = """
                        SELECT SUM(amount) FROM cost_database
                        WHERE function = $1 AND year = $2 AND scenario = $3 AND cost_text = $4
                    """
                    fy25 = await self.conn.fetchval(
                        base_query, function, "FY25", "Actual", cost_text
                    )
                    fy26 = await self.conn.fetchval(
                        base_query, function, "FY26", "Budget1", cost_text
                    )
                else:
                    base_query = """
                        SELECT SUM(amount) FROM cost_database
                        WHERE function = $1 AND year = $2 AND scenario = $3
                    """
                    fy25 = await self.conn.fetchval(
                        base_query, function, "FY25", "Actual"
                    )
                    fy26 = await self.conn.fetchval(
                        base_query, function, "FY26", "Budget1"
                    )

            if fy25 is None or fy26 is None:
                return QueryResult(
                    success=False,
                    data=None,
                    message="Insufficient data for trend analysis",
                    query_type="trend",
                )

            change = float(fy26) - float(fy25)
            change_pct = (change / float(fy25)) * 100 if fy25 != 0 else 0

            result_data = {
                "function": function,
                "cost_text": cost_text,
                "party_type": party_type,
                "party_value": party_value,
                "fy25_actual": float(fy25),
                "fy26_budget": float(fy26),
                "change": change,
                "change_percentage": round(change_pct, 2),
                "trend": "increase" if change > 0 else "decrease",
            }

            direction = "increased" if change > 0 else "decreased"
            message = f"{direction} by {abs(change):,.0f} ({abs(change_pct):.1f}%)"

            return QueryResult(
                success=True, data=result_data, message=message, query_type="trend"
            )

        except Exception as e:
            return QueryResult(
                success=False,
                data=None,
                message=f"Query error: {str(e)}",
                query_type="trend",
            )


def format_output(result: QueryResult, json_output: bool = False) -> str:
    """Format query result for output"""
    if json_output:
        return json.dumps(
            {
                "success": result.success,
                "message": result.message,
                "query_type": result.query_type,
                "data": result.data,
            },
            indent=2,
            default=str,
        )

    if not result.success:
        return f"Error: {result.message}"

    lines = [f"Query Type: {result.query_type}", f"Message: {result.message}", ""]

    if result.data:
        lines.append("Data:")
        if isinstance(result.data, dict):
            for key, value in result.data.items():
                if key != "breakdown":
                    lines.append(f"  {key}: {value}")

            if "breakdown" in result.data:
                lines.append("\n  Breakdown:")
                for item in result.data["breakdown"]:
                    lines.append(f"    - {item['cost_text']}: {item['amount']:,.2f}")

    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(
        description="Cost Allocation Query Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Query HR cost for FY26 Budget
  python cost_allocation.py query --type cost --year FY26 --scenario Budget1 --function HR
  
  # Query IT Allocation to CT
  python cost_allocation.py query --type allocation --year FY25 --scenario Actual --function "IT Allocation" --party-bl CT
  
  # Query trend for Procurement
  python cost_allocation.py query --type trend --function Procurement --cost-text "Pooling & MPC"
  
  # JSON output (for AI integration)
  python cost_allocation.py query --type cost --year FY26 --scenario Budget1 --function HR --json
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Query command
    query_parser = subparsers.add_parser("query", help="Execute a query")
    query_parser.add_argument(
        "--type",
        required=True,
        choices=["cost", "allocation", "trend"],
        help="Query type",
    )
    query_parser.add_argument("--year", help="Fiscal year (FY24, FY25, FY26)")
    query_parser.add_argument("--scenario", help="Scenario (Actual, Budget1)")
    query_parser.add_argument("--function", required=True, help="Function name")
    query_parser.add_argument("--cost-text", help="Specific cost text filter")
    query_parser.add_argument("--month", help="Specific month filter (e.g., Oct, Nov)")
    query_parser.add_argument("--party-bl", help="Business line party (for allocation)")
    query_parser.add_argument("--party-cc", help="Cost center party (for allocation)")
    query_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Test command
    test_parser = subparsers.add_parser("test", help="Run test cases")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "test":
        # Import and run tests
        from test_cost_allocation import run_all_tests, print_results

        results = await run_all_tests()
        all_passed = print_results(results)
        sys.exit(0 if all_passed else 1)

    elif args.command == "query":
        manager = await CostAllocationManager().connect()

        try:
            if args.type == "cost":
                if not args.year or not args.scenario:
                    print("Error: --year and --scenario required for cost query")
                    sys.exit(1)

                result = await manager.query_cost(
                    year=args.year,
                    scenario=args.scenario,
                    function=args.function,
                    cost_text=args.cost_text,
                    month=args.month,
                )

            elif args.type == "allocation":
                if not args.year or not args.scenario:
                    print("Error: --year and --scenario required for allocation query")
                    sys.exit(1)

                if args.party_bl:
                    result = await manager.query_allocation(
                        year=args.year,
                        scenario=args.scenario,
                        function=args.function,
                        party_type="bl",
                        party_value=args.party_bl,
                        cost_text=args.cost_text,
                        month=args.month,
                    )
                elif args.party_cc:
                    result = await manager.query_allocation(
                        year=args.year,
                        scenario=args.scenario,
                        function=args.function,
                        party_type="cc",
                        party_value=args.party_cc,
                        cost_text=args.cost_text,
                        month=args.month,
                    )
                else:
                    print(
                        "Error: --party-bl or --party-cc required for allocation query"
                    )
                    sys.exit(1)

            elif args.type == "trend":
                result = await manager.query_trend(
                    function=args.function,
                    cost_text=args.cost_text,
                    party_type=(
                        "bl" if args.party_bl else ("cc" if args.party_cc else None)
                    ),
                    party_value=args.party_bl or args.party_cc,
                )

            print(format_output(result, args.json))
            sys.exit(0 if result.success else 1)

        finally:
            await manager.close()


if __name__ == "__main__":
    asyncio.run(main())
