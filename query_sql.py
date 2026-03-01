import asyncio
import asyncpg
import sys

async def query():
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            database='cost_allocation',
            user='postgres',
            password='123456'
        )
        
        # 查询 cost 表
        cost_sql = """
        SELECT cost_amount, allocation_key, party_cc, party_bl 
        FROM cost_database 
        WHERE year = 'FY26' 
          AND scenario = 'Budget1' 
          AND month = '10' 
          AND cost_text = '7092 GS IT_End user'
        """
        cost_row = await conn.fetchrow(cost_sql)
        print('=== COST 表查询结果 ===', flush=True)
        if cost_row:
            print(f'原始成本: {cost_row[0]}', flush=True)
            print(f'Allocation Key: {cost_row[1]}', flush=True)
            print(f'Party CC: {cost_row[2]}', flush=True)
            print(f'Party BL: {cost_row[3]}', flush=True)
            cost_amount = cost_row[0]
            key = cost_row[1]
        else:
            print('未找到记录', flush=True)
            cost_amount = None
            key = None
        
        # 查询 rate 表
        rate_sql = """
        SELECT rate_no 
        FROM rate_table 
        WHERE key = 'WCW' 
          AND cc = '412011' 
          AND scenario = 'Budget1' 
          AND year = 'FY26' 
          AND month = 'Oct'
        """
        rate_row = await conn.fetchrow(rate_sql)
        print('\n=== RATE 表查询结果 ===', flush=True)
        if rate_row:
            print(f'分摊比例: {rate_row[0]}', flush=True)
            rate_no = rate_row[0]
        else:
            print('未找到记录', flush=True)
            rate_no = None
        
        # 计算结果
        if cost_amount and rate_no:
            result = cost_amount * rate_no
            print(f'\n=== 计算结果 ===', flush=True)
            print(f'{cost_amount} × {rate_no} = {result}', flush=True)
        
        await conn.close()
    except Exception as e:
        print(f'错误: {e}', flush=True)

asyncio.run(query())
