from flask import Flask, render_template, request, redirect, session
import pyodbc

app = Flask(__name__)
app.secret_key = 'super_secret_mmu_key' # Needed for tracking who is logged in

def get_db_connection():
    return pyodbc.connect(
        'Driver={SQL Server};'
        'Server=LAPTOP-36TSQ44S\MSSQLSERVER01;'
        'Database=LibraryDB;'
        'Trusted_Connection=yes;'
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT UserID, Username, PasswordHash, Role FROM Users WHERE Username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and user.PasswordHash == password:
            session['user_id'] = user.UserID
            session['username'] = user.Username
            session['role'] = user.Role
            
            if user.Role in ['Librarian', 'Staff']:
                return redirect('/admin_panel')
            else:
                return redirect('/user_panel')
        return "<h1>Invalid Credentials</h1>"
    return render_template('login.html')

# --- USER PANEL (For Members) ---
@app.route('/user_panel')
def user_panel():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Books WHERE Status = 'Available'")
    catalog = cursor.fetchall()
    conn.close()
    return render_template('member.html', catalog=catalog)

@app.route('/search', methods=['POST'])
def search():
    query = request.form['query']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Books WHERE Title LIKE ?", ('%' + query + '%',))
    results = cursor.fetchall()
    conn.close()
    return render_template('member.html', catalog=results)

# --- ADMIN PANEL (For Librarians & Staff) ---
@app.route('/admin_panel')
def admin_panel():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Books")
    books = cursor.fetchall()
    cursor.execute("SELECT UserID, Username, Role FROM Users")
    users = cursor.fetchall()
    conn.close()
    return render_template('librarian.html', books=books, users=users)

@app.route('/manage_users', methods=['POST'])
def manage_users():
    # Logic to add/remove users as per the manageUsers component
    return redirect('/admin_panel')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)