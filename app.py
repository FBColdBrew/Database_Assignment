from flask import Flask, render_template, request, redirect, session
import pyodbc
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_mmu_key'

# --- DATABASE CONNECTION ---
def get_db_connection():
    return pyodbc.connect(
        'Driver={SQL Server};'
        'Server=LAPTOP-36TSQ44S\\MSSQLSERVER01;'
        'Database=SecureLibraryDB;'
        'Trusted_Connection=yes;'
    )

# --- ROUTES ---
@app.route('/')
def index():
    return redirect('/login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Adam's SQL INSERT query will go here later to save the new user
        return redirect('/login')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # This is the database logic that was missing!
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT UserID, Email, PasswordHash, UserRole FROM Users WHERE Email = ?', (email,))
        user = cursor.fetchone()
        conn.close()
        
        # UPGRADED SECURITY: Checking hashed passwords
        if user and check_password_hash(user.PasswordHash, password):
            session['user_id'] = user.UserID
            session['email'] = user.Email
            session['role'] = user.UserRole
            
            # Redirect to the correct dashboard based on role
            if user.UserRole in ['Librarian', 'Admin']:
                return redirect('/admin_panel')
            else:
                return redirect('/user_panel')
                
        return "<h1>Invalid Credentials</h1>"
        
    return render_template('login.html')

@app.route('/user_panel')
def user_panel():
    if 'user_id' not in session:
        return redirect('/login')
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Books WHERE AvailabilityStatus = 'Available'")
    catalog = cursor.fetchall()
    conn.close()
    
    return render_template('member.html', catalog=catalog)

@app.route('/admin_panel')
def admin_panel():
    if session.get('role') not in ['Librarian', 'Admin']:
        return "<h1>Access Denied. Admins Only.</h1>", 403
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Books")
    books = cursor.fetchall()
    
    # Using FullName instead of Username to match our SQL schema
    cursor.execute("SELECT UserID, FullName, Email, UserRole FROM Users")
    users = cursor.fetchall()
    conn.close()
    
    return render_template('admin.html', books=books, users=users)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True)