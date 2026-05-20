import pyodbc
from werkzeug.security import generate_password_hash

print("Connecting to database...")

# 1. Connect to your specific SQL Server instance
conn = pyodbc.connect(
    'Driver={SQL Server};'
    'Server=PREDATOR-FAHMI\\MSSQLSERVER01;'
    'Database=LibraryDB;'
    'Trusted_Connection=yes;'
)
cursor = conn.cursor()

# 2. Create the secure hash for the password 'admin123'
secure_hash = generate_password_hash('admin123')

try:
    # 3. Inject the new Admin into the database
    cursor.execute("""
        INSERT INTO Users (Name, Email, Username, Password, Role, Wallet) 
        VALUES ('System Admin', 'admin@mmu.edu.my', 'admin', ?, 'Admin', 0.00)
    """, (secure_hash,))
    
    conn.commit()
    print("=========================================")
    print("✅ SUCCESS: Admin Account Created!")
    print("👉 Username: admin")
    print("👉 Password: admin123")
    print("=========================================")

except pyodbc.IntegrityError:
    print("⚠️ Error: An account with the username 'admin' already exists in the database.")
except Exception as e:
    print("❌ An unexpected error occurred:", e)

finally:
    conn.close()
