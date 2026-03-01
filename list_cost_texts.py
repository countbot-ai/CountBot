import asyncio
import asyncpg
import os

async def list_cost_texts():
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', 5432),
            database=os.getenv('POSTGRES_DB', 'cost_allocation'),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123456')
        )
        print("Connected to database")
        
        # Query distinct cost_text
        rows = await conn.fetch('SELECT DISTINCT cost_text, function FROM cost_database ORDER BY function, cost_text')
        
        print("\nAvailable cost_text values (grouped by function):")
        print("-" * 50)
        
        current_function = None
        for row in rows:
            cost_text = row['cost_text']
            function = row['function']
            
            if function != current_function:
                print(f"\nFunction: {function}")
                current_function = function
            
            print(f"  - {cost_text}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            await conn.close()

if __name__ == "__main__":
    asyncio.run(list_cost_texts())
