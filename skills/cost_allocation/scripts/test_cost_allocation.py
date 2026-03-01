"""
Cost Allocation Skill Test Cases

Test cases based on Excel file: Function cost allocation analysis to IT 20260104
Validates PostgreSQL database queries for cost allocation calculations.

Run tests:
    python -m pytest tests/test_cost_allocation.py -v
    
Or run directly:
    python skills/cost_allocation/scripts/test_cost_allocation.py
"""

import asyncio
import asyncpg
import os
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

# Test Configuration
TEST_DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'cost_allocation'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '123456')
}


@dataclass
class TestResult:
    """Test result container"""
    name: str
    expected: any
    actual: any
    passed: bool
    tolerance: float = 1.0


async def get_db_connection():
    """Get database connection for testing"""
    return await asyncpg.connect(**TEST_DB_CONFIG)


async def test_q1_it_services():
    """
    Q1: IT成本包含哪些服务？分摊关键是什么？
    
    Expected: List of IT services and their allocation keys
    """
    conn = await get_db_connection()
    try:
        # Get IT Allocation services
        services = await conn.fetch("""
            SELECT DISTINCT cost_text, key
            FROM cost_database
            WHERE function = 'IT Allocation'
            ORDER BY cost_text
        """)
        
        # Should have at least one IT Allocation service
        assert len(services) >= 1, "Should have IT Allocation services"
        
        # Check that 480056 Cycle is one of the keys
        keys = [s['key'] for s in services]
        assert '480056 Cycle' in keys, "Should have 480056 Cycle as allocation key"
        
        return TestResult(
            name="Q1: IT Services and Allocation Keys",
            expected="IT Allocation services with 480056 Cycle key",
            actual=f"Found {len(services)} services",
            passed=True
        )
    finally:
        await conn.close()


async def test_q2_fy26_hr_cost():
    """
    Q2: FY26预算中HR成本是多少？
    
    Expected: 12,054,383
    """
    conn = await get_db_connection()
    try:
        result = await conn.fetchval("""
            SELECT SUM(amount) 
            FROM cost_database 
            WHERE year = 'FY26' 
            AND scenario = 'Budget1' 
            AND function = 'HR'
        """)
        
        expected = Decimal('12054383')
        actual = result or Decimal('0')
        diff = abs(float(actual) - float(expected))
        passed = diff < 1.0
        
        return TestResult(
            name="Q2: FY26 Budget HR Cost",
            expected=float(expected),
            actual=float(actual),
            passed=passed,
            tolerance=1.0
        )
    finally:
        await conn.close()


async def test_q3_fy25_it_allocation_to_ct():
    """
    Q3: FY25实际分配给CT的IT成本是多少？
    
    Expected: 7,847,136.18
    
    Calculation: SUM(ABS(cost_amount) * rate_no) 
                 for IT Allocation, FY25 Actual, CT
    """
    conn = await get_db_connection()
    try:
        result = await conn.fetchval("""
            SELECT SUM(ABS(cd.amount) * rt.rate_no)
            FROM cost_database cd
            JOIN rate_table rt ON cd.key = rt.key 
                AND cd.year = rt.year 
                AND cd.scenario = rt.scenario 
                AND cd.month = rt.month
            WHERE cd.year = 'FY25' 
            AND cd.scenario = 'Actual' 
            AND cd.function = 'IT Allocation'
            AND rt.bl = 'CT'
        """)
        
        expected = Decimal('7847136.18')
        actual = result or Decimal('0')
        diff = abs(float(actual) - float(expected))
        passed = diff < 100.0  # Allow 100 tolerance due to rounding
        
        return TestResult(
            name="Q3: FY25 IT Allocation to CT",
            expected=float(expected),
            actual=float(actual),
            passed=passed,
            tolerance=100.0
        )
    finally:
        await conn.close()


async def test_q4_procurement_change():
    """
    Q4: Procurement Cost Change from FY25 Actual to FY26 Budget
    
    Expected: +96,467 (+5%)
    
    Note: Based on Excel, this is specifically for 'Pooling & MPC' cost_text
    """
    conn = await get_db_connection()
    try:
        fy25 = await conn.fetchval("""
            SELECT SUM(amount) 
            FROM cost_database 
            WHERE year = 'FY25' 
            AND scenario = 'Actual' 
            AND function = 'Procurement'
            AND cost_text = 'Pooling & MPC'
        """)
        
        fy26 = await conn.fetchval("""
            SELECT SUM(amount) 
            FROM cost_database 
            WHERE year = 'FY26' 
            AND scenario = 'Budget1' 
            AND function = 'Procurement'
            AND cost_text = 'Pooling & MPC'
        """)
        
        if fy25 is None or fy26 is None:
            return TestResult(
                name="Q4: Procurement Pooling & MPC Change",
                expected="FY25: 1,922,533, FY26: 2,019,000, Change: +96,467",
                actual="Missing data",
                passed=False
            )
        
        change = float(fy26) - float(fy25)
        change_pct = (change / float(fy25)) * 100 if fy25 != 0 else 0
        
        expected_change = 96467
        expected_pct = 5.0
        
        passed = abs(change - expected_change) < 100 and abs(change_pct - expected_pct) < 0.5
        
        return TestResult(
            name="Q4: Procurement Pooling & MPC Change",
            expected=f"Change: +{expected_change} (+{expected_pct}%)",
            actual=f"Change: +{change:.0f} (+{change_pct:.1f}%)",
            passed=passed,
            tolerance=100.0
        )
    finally:
        await conn.close()


async def test_q5_hr_allocation_to_413001():
    """
    Q5: HR Allocation to CC 413001 Change from FY25 Actual to FY26 Budget
    
    Expected: -24,634 (-10.2%)
    
    Calculation: SUM(ABS(cost_amount) * rate_no) for HR Allocation, CC=413001
    """
    conn = await get_db_connection()
    try:
        fy25 = await conn.fetchval("""
            SELECT SUM(ABS(cd.amount) * rt.rate_no)
            FROM cost_database cd
            JOIN rate_table rt ON cd.key = rt.key 
                AND cd.year = rt.year 
                AND cd.scenario = rt.scenario 
                AND cd.month = rt.month
            WHERE cd.year = 'FY25' 
            AND cd.scenario = 'Actual' 
            AND cd.function = 'HR Allocation'
            AND rt.cc = '413001'
        """)
        
        fy26 = await conn.fetchval("""
            SELECT SUM(ABS(cd.amount) * rt.rate_no)
            FROM cost_database cd
            JOIN rate_table rt ON cd.key = rt.key 
                AND cd.year = rt.year 
                AND cd.scenario = rt.scenario 
                AND cd.month = rt.month
            WHERE cd.year = 'FY26' 
            AND cd.scenario = 'Budget1' 
            AND cd.function = 'HR Allocation'
            AND rt.cc = '413001'
        """)
        
        if fy25 is None or fy26 is None:
            return TestResult(
                name="Q5: HR Allocation to 413001 Change",
                expected="FY25: 241,613, FY26: 216,979, Change: -24,634 (-10.2%)",
                actual="Missing data",
                passed=False
            )
        
        change = float(fy26) - float(fy25)
        change_pct = (change / float(fy25)) * 100 if fy25 != 0 else 0
        
        expected_change = -24634
        expected_pct = -10.2
        
        passed = abs(change - expected_change) < 100 and abs(change_pct - expected_pct) < 0.5
        
        return TestResult(
            name="Q5: HR Allocation to 413001 Change",
            expected=f"Change: {expected_change} ({expected_pct}%)",
            actual=f"Change: {change:.0f} ({change_pct:.1f}%)",
            passed=passed,
            tolerance=100.0
        )
    finally:
        await conn.close()


async def run_all_tests():
    """Run all test cases"""
    tests = [
        test_q1_it_services,
        test_q2_fy26_hr_cost,
        test_q3_fy25_it_allocation_to_ct,
        test_q4_procurement_change,
        test_q5_hr_allocation_to_413001,
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            results.append(TestResult(
                name=test.__name__,
                expected="Success",
                actual=f"Error: {str(e)}",
                passed=False
            ))
    
    return results


def print_results(results: list):
    """Print test results in a formatted way"""
    print("\n" + "=" * 80)
    print("COST ALLOCATION SKILL TEST RESULTS")
    print("=" * 80)
    
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)
    
    for i, result in enumerate(results, 1):
        status = "PASS" if result.passed else "FAIL"
        status_symbol = "[OK]" if result.passed else "[X]"
        
        print(f"\n{i}. {result.name}")
        print(f"   Status: {status_symbol} {status}")
        print(f"   Expected: {result.expected}")
        print(f"   Actual:   {result.actual}")
        if not result.passed:
            print(f"   Tolerance: ±{result.tolerance}")
    
    print("\n" + "=" * 80)
    print(f"SUMMARY: {passed_count}/{total_count} tests passed")
    print("=" * 80 + "\n")
    
    return passed_count == total_count


if __name__ == "__main__":
    async def main():
        results = await run_all_tests()
        all_passed = print_results(results)
        exit(0 if all_passed else 1)
    
    asyncio.run(main())
