from flask import Flask, render_template, request, redirect, session, flash
from datetime import datetime, date, timedelta
import pyodbc
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_mmu_key'

def get_db_connection():
    return pyodbc.connect(
        'Driver={SQL Server};'
        'Server=PREDATOR-FAHMI\\MSSQLSERVER01;'
        'Database=LibraryDB;'
        'Trusted_Connection=yes;'
    )

@app.route('/')
def index():
    data = {}
    if 'user_id' in session:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if session['role'] == 'Admin':
            cursor.execute("""
                SELECT B.ID, B.Title, B.Genre, B.Status, 
                (SELECT TOP 1 U.Name FROM Loans L JOIN Users U ON L.UserID = U.ID WHERE L.BookID = B.ID ORDER BY L.ID DESC) as CurrentUser
                FROM Books B
            """)
            data['books'] = cursor.fetchall()
            
            # Adam's Update: Added ICNumber to the Users query
            cursor.execute("""
                SELECT 
                    U.ID, U.Name, U.ICNumber, U.Username, U.Role, U.Wallet,
                    (SELECT TOP 1 B.Title + ' (Borrowed: ' + FORMAT(L.BorrowDate, 'dd/MM') + ', Due: ' + FORMAT(L.DueDate, 'dd/MM') + ')' 
                     FROM Loans L JOIN Books B ON L.BookID = B.ID 
                     WHERE L.UserID = U.ID AND L.Status != 'Returned' 
                     ORDER BY L.BorrowDate DESC) as LoanInfo,
                    (SELECT COUNT(*) FROM Loans L 
                     WHERE L.UserID = U.ID 
                     AND L.ReturnDate IS NULL 
                     AND (L.DueDate < CAST(GETDATE() AS DATE) OR L.Status = 'Late' OR L.Fine > 0)) as PenaltyCount
                FROM Users U
            """)
            data['users'] = cursor.fetchall()

            cursor.execute("SELECT Value FROM Settings WHERE Name = 'LateFee'")
            data['penalty_rate'] = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT L.ID, U.Name as UserName, B.Title as BookTitle, L.BorrowDate, L.DueDate, L.Status 
                FROM Loans L 
                JOIN Users U ON L.UserID = U.ID 
                JOIN Books B ON L.BookID = B.ID
            """)
            data['logs'] = cursor.fetchall()

            # Adam's Update: Added the LoginLogs query for the Admin Dashboard
            cursor.execute("""
                SELECT Username, FORMAT(AttemptTime, 'dd/MM/yyyy HH:mm:ss') as AttemptTime, Status, Reason
                FROM LoginLogs
                ORDER BY ID DESC
            """)
            data['login_logs'] = cursor.fetchall()
            
        else:
            # Member Data
            cursor.execute("SELECT ID, Title, Genre, Status FROM Books")
            data['books'] = cursor.fetchall()
            
            cursor.execute("SELECT Name, Email, Wallet FROM Users WHERE ID = ?", (session['user_id'],))
            data['user'] = cursor.fetchone()
            
            cursor.execute("SELECT Value FROM Settings WHERE Name = 'LateFee'")
            penalty_rate = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT L.ID as LoanID, B.Title, L.DueDate, L.Status 
                FROM Loans L 
                JOIN Books B ON L.BookID = B.ID 
                WHERE L.UserID = ? AND L.Status != 'Returned'
            """, (session['user_id'],))
            raw_loans = cursor.fetchall()
            
            my_loans = []
            today = date.today() 
            
            for loan in raw_loans:
                if isinstance(loan.DueDate, str):
                    actual_date = datetime.strptime(loan.DueDate, '%Y-%m-%d').date()
                else:
                    try:
                        actual_date = loan.DueDate.date()
                    except AttributeError:
                        actual_date = loan.DueDate
                my_date_str = actual_date.strftime('%d/%m/%Y')
                
                days_late = (today - actual_date).days
                status = loan.Status
                fine = 0.00
                
                if days_late > 0:
                    status = 'Late'
                    fine = days_late * penalty_rate
                    
                my_loans.append({
                    'LoanID': loan.LoanID,
                    'Title': loan.Title,
                    'DueDate': my_date_str, 
                    'Status': status,
                    'Fine': fine
                })
                
            data['my_loans'] = my_loans
            
        conn.close()
    return render_template('prototype.html', data=data)

# --- LOGIN / LOGOUT ---
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Grab the user's details, including the hashed password
    cursor.execute('SELECT ID, Username, Password, Role FROM Users WHERE Username = ?', (username,))
    user = cursor.fetchone()
    
    status = ""
    reason = ""
    
    # --- YOUR SECURITY + ADAM'S LOGGING MERGED ---
    if not user:
        status = "Failed"
        reason = "Unknown Username"
        flash("The username or password is wrong!", "error")
        
    # YOUR FIX: Using Werkzeug to securely check the hash!
    elif not check_password_hash(user.Password, password):
        status = "Failed"
        reason = "Incorrect Password"
        flash("The username or password is wrong!", "error")
        
    else:
        status = "Success"
        reason = "Valid Login"
        session['user_id'] = user.ID
        session['username'] = user.Username
        session['role'] = user.Role

    # ADAM'S FEATURE: Record the attempt in the database
    cursor.execute("INSERT INTO LoginLogs (Username, Status, Reason) VALUES (?, ?, ?)", (username, status, reason))
    
    conn.commit()
    conn.close()
    
    return redirect('/')

@app.route('/register', methods=['POST'])
def register():
    name = request.form['name']
    ic_number = request.form['ic_number'] # Adam's new IC Number field
    email = request.form['email']
    username = request.form['username']
    password = request.form['password']
    
    # YOUR SECURITY: Bring the hashing back!
    hashed_password = generate_password_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # MERGE: Insert both the IC number AND the hashed password
        cursor.execute("""
            INSERT INTO Users (Name, ICNumber, Email, Username, Password, Role, Wallet) 
            VALUES (?, ?, ?, ?, ?, 'Member', 0.00)
        """, (name, ic_number, email, username, hashed_password))
        conn.commit()
        flash("Registration successful! Please log in.", "success")
    except Exception as e:
        print("Registration Error:", e)
        flash("Error: Username or Email already exists!", "error")
        
    conn.close()
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# --- MEMBER FUNCTIONS ---
@app.route('/borrow', methods=['POST'])
def borrow():
    book_id = request.form['book_id']
    due_date = request.form['due_date'] 
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Loans (UserID, BookID, DueDate, Status) VALUES (?, ?, ?, 'Active')", 
                   (user_id, book_id, due_date))
    cursor.execute("UPDATE Books SET Status = 'Borrowed' WHERE ID = ?", (book_id,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/return_book', methods=['POST'])
def return_book():
    loan_id = request.form['loan_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT BookID FROM Loans WHERE ID = ?", (loan_id,))
    book_id = cursor.fetchone()[0]
    
    cursor.execute("UPDATE Loans SET Status = 'Returned', ReturnDate = GETDATE() WHERE ID = ?", (loan_id,))
    cursor.execute("UPDATE Books SET Status = 'Available' WHERE ID = ?", (book_id,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/pay_penalty', methods=['POST'])
def pay_penalty():
    loan_id = request.form['loan_id']
    fine_amount = float(request.form['fine_amount'])
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT Wallet FROM Users WHERE ID = ?", (user_id,))
    wallet = cursor.fetchone()[0]
    
    if wallet >= fine_amount:
        cursor.execute("UPDATE Users SET Wallet = Wallet - ? WHERE ID = ?", (fine_amount, user_id))
        cursor.execute("SELECT BookID FROM Loans WHERE ID = ?", (loan_id,))
        book_id = cursor.fetchone()[0]
        cursor.execute("UPDATE Loans SET Status = 'Returned', ReturnDate = GETDATE(), Fine = ? WHERE ID = ?", (fine_amount, loan_id))
        cursor.execute("UPDATE Books SET Status = 'Available' WHERE ID = ?", (book_id,))
        conn.commit()
    else:
        print("Not enough money in wallet!")
        
    conn.close()
    return redirect('/')

@app.route('/reload', methods=['POST'])
def reload():
    amount = float(request.form['amount'])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Users SET Wallet = Wallet + ? WHERE ID = ?", (amount, session['user_id']))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return redirect('/login')

    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']

    if new_password != confirm_password:
        flash("Error: New passwords do not match!", "error")
        return redirect('/') 

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT Password FROM Users WHERE ID = ?", (session['user_id'],))
    user = cursor.fetchone()

    # YOUR SECURITY: Upgraded change password to securely check and hash the new one!
    if user and check_password_hash(user.Password, current_password):
        hashed_new = generate_password_hash(new_password)
        cursor.execute("UPDATE Users SET Password = ? WHERE ID = ?", (hashed_new, session['user_id']))
        conn.commit()
        flash("Success: Password updated successfully!", "success")
    else:
        flash("The current password is wrong!", "error")
        
    conn.close()
    return redirect('/')

# --- ADMIN FUNCTIONS ---
@app.route('/add_book', methods=['POST'])
def add_book():
    title = request.form['title']
    genre = request.form['genre'] 
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Books (Title, Genre, Status) VALUES (?, ?, 'Available')", (title, genre))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/edit_book', methods=['POST'])
def edit_book():
    if session.get('role') != 'Admin':
        return redirect('/')

    book_id = request.form['book_id']
    new_title = request.form['new_title']
    new_genre = request.form['new_genre']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Books SET Title = ?, Genre = ? WHERE ID = ?", (new_title, new_genre, book_id))
    conn.commit()
    conn.close()
    
    return redirect('/')

@app.route('/delete_book', methods=['POST'])
def delete_book():
    if session.get('role') != 'Admin':
        return redirect('/')

    book_id = request.form['book_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM Loans WHERE BookID = ?", (book_id,))
        cursor.execute("DELETE FROM Books WHERE ID = ?", (book_id,))
        conn.commit()
        flash("Book and its loan history deleted successfully!", "success")
    except Exception as e:
        conn.rollback() 
        flash("Error: System failed to delete the book.", "error")
        print(e)
        
    conn.close()
    return redirect('/')

@app.route('/update_penalty', methods=['POST'])
def update_penalty():
    new_rate = request.form['rate']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Settings SET Value = ? WHERE Name = 'LateFee'", (new_rate,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/delete_user', methods=['POST'])
def delete_user():
    if session.get('role') != 'Admin':
        return redirect('/')

    target_id = request.form['user_id']
    
    if int(target_id) == session.get('user_id'):
        flash("Error: You cannot delete your own account!", "error")
        return redirect('/')

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM Loans WHERE UserID = ?", (target_id,))
        cursor.execute("DELETE FROM Users WHERE ID = ?", (target_id,))
        conn.commit()
        flash("User and their history deleted successfully!", "success")
    except Exception as e:
        conn.rollback()
        flash("Error: Could not delete user.", "error")
        print(e)
        
    conn.close()
    return redirect('/')

@app.route('/set_role', methods=['POST'])
def set_role():
    if session.get('role') != 'Admin':
        return redirect('/')

    target_id = request.form['user_id']
    new_role = request.form['new_role']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Users SET Role = ? WHERE ID = ?", (new_role, target_id))
    conn.commit()
    conn.close()
    
    flash(f"User role updated to {new_role}!", "success")
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
