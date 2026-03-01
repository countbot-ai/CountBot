import asyncio
import asyncpg

async def query():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='cost_allocation',
        user='postgres',
        password='123456'
    )
    
    # 查 cost 表结构
    rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'cost_database'")
    print('=== cost_database 表字段 ===', flush=True)
    for row in rows:
        print(f'  {row[0]}', flush=True)
    
    # 查 rate 表结构
    rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'rate_table'")
    print('\n=== rate_table 表字段 ===', flush=True)
    for row in rows:
        print(f'  {row[0]}', flush=True)
    
    # 查一条 cost 表数据看看
    row = await conn.fetchrow("SELECT * FROM cost_database WHERE cost_text = '7092 GS IT_End user' LIMIT 1")
    print('\n=== cost_database 样例数据 ===', flush=True)
    if row:
        for i, col in enumerate(row):
            print(f'  字段{i}: {col}', flush=True)
    
    await conn.close()

asyncio.run(query())
