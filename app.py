from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import os
import threading
import email_service

app = Flask(__name__, static_folder='.', static_url_path='', template_folder='templates')
app.secret_key = 'desgrow_secret'

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "123"

@app.before_request
def require_login():
    if request.path.startswith('/admin'):
        if not session.get('logged_in'):
            return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash('Sai tài khoản hoặc mật khẩu!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

DB_PATH = 'brain.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Auto-migrate db: add email column to customers if not exists
try:
    _conn = sqlite3.connect(DB_PATH)
    _conn.execute('ALTER TABLE customers ADD COLUMN email TEXT')
    _conn.commit()
    _conn.close()
except sqlite3.OperationalError:
    pass

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/thanhtoan')
def thanhtoan():
    return render_template('thanhtoan.html')

@app.route('/admin')
def admin():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products').fetchall()
    customers = conn.execute('SELECT * FROM customers').fetchall()
    orders = conn.execute('''
        SELECT orders.id, products.name as product_name, customers.name as customer_name,
               orders.amount, orders.status, orders.ordered_at
        FROM orders
        JOIN products ON orders.product_id = products.id
        JOIN customers ON orders.customer_id = customers.id
    ''').fetchall()
    conn.close()
    return render_template('admin.html', products=products, customers=customers, orders=orders)

@app.route('/admin/products/add', methods=('POST',))
def add_product():
    name = request.form['name']
    price = request.form['price']
    description = request.form.get('description', '')
    stock = request.form.get('stock', 0)
    conn = get_db_connection()
    conn.execute('INSERT INTO products (name, price, description, stock) VALUES (?, ?, ?, ?)',
                 (name, price, description, stock))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/products/delete/<int:id>', methods=('POST',))
def delete_product(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM products WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/customers/add', methods=('POST',))
def add_customer():
    name = request.form['name']
    phone = request.form['phone']
    zalo = request.form.get('zalo', '')
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO customers (name, phone, zalo, registered_at) VALUES (?, ?, ?, datetime("now"))',
                     (name, phone, zalo))
        conn.commit()
    except sqlite3.IntegrityError:
        flash('Số điện thoại đã tồn tại!')
    finally:
        conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/customers/delete/<int:id>', methods=('POST',))
def delete_customer(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM customers WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/orders/add', methods=('POST',))
def add_order():
    product_id = request.form['product_id']
    customer_id = request.form['customer_id']
    amount = request.form['amount']
    conn = get_db_connection()
    
    # Khi thêm đơn hàng mới -> trừ đi 1 đơn vị tồn kho
    conn.execute('UPDATE products SET stock = stock - 1 WHERE id = ? AND stock > 0', (product_id,))
    
    conn.execute('INSERT INTO orders (product_id, customer_id, amount, ordered_at) VALUES (?, ?, ?, datetime("now"))',
                 (product_id, customer_id, amount))
    conn.commit()

    # Thêm code gửi email xác nhận đặt hàng
    cur = conn.execute('SELECT name, email FROM customers WHERE id = ?', (customer_id,))
    customer = cur.fetchone()
    cur = conn.execute('SELECT name FROM products WHERE id = ?', (product_id,))
    product = cur.fetchone()
    conn.close()
    
    if customer and customer['email'] and product:
        threading.Thread(target=email_service.send_order_confirmation, args=(customer['name'], customer['email'], product['name'], float(amount))).start()
        
    return redirect(url_for('admin'))

@app.route('/admin/orders/status/<int:id>', methods=('POST',))
def update_order_status(id):
    status = request.form['status']
    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', (status, id))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

from flask import jsonify

@app.route('/api/products', methods=['GET'])
def api_products():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products').fetchall()
    conn.close()
    return jsonify([dict(p) for p in products])

@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    data = request.json
    name = data.get('name')
    phone = data.get('phone')
    email = data.get('email', '')
    product_id = data.get('product_id')
    
    conn = get_db_connection()
    cur = conn.execute('SELECT id FROM customers WHERE phone = ?', (phone,))
    customer = cur.fetchone()
    if customer:
        customer_id = customer['id']
        if email:
            conn.execute('UPDATE customers SET email = ? WHERE id = ?', (email, customer_id))
    else:
        cur = conn.execute('INSERT INTO customers (name, phone, email, registered_at) VALUES (?, ?, ?, datetime("now"))', (name, phone, email))
        customer_id = cur.lastrowid
        # Gửi chuỗi email chăm sóc nếu có email
        if email:
            threading.Thread(target=email_service.send_waitlist_sequence, args=(name, email)).start()
        
    cur = conn.execute('SELECT price, stock FROM products WHERE id = ?', (product_id,))
    product = cur.fetchone()
    if not product:
        conn.close()
        return jsonify({"error": "Product not found"}), 400
        
    price = product['price']
    conn.execute('UPDATE products SET stock = stock - 1 WHERE id = ? AND stock > 0', (product_id,))
    
    cur = conn.execute('INSERT INTO orders (product_id, customer_id, amount, ordered_at) VALUES (?, ?, ?, datetime("now"))',
                 (product_id, customer_id, price))
    order_id = cur.lastrowid
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "order_id": order_id,
        "amount": price,
        "description": f"DH{order_id}"
    })

@app.route('/api/order-status/<int:id>', methods=['GET'])
def api_order_status(id):
    conn = get_db_connection()
    cur = conn.execute('SELECT status FROM orders WHERE id = ?', (id,))
    order = cur.fetchone()
    conn.close()
    if order:
        return jsonify({"status": order['status']})
    return jsonify({"error": "Order not found"}), 404

@app.route('/api/sepay-webhook', methods=['POST'])
def api_sepay_webhook():
    import re
    data = request.json
    content = data.get('content', '')
    match = re.search(r'DH(\d+)', str(content).upper())
    if match:
        order_id = int(match.group(1))
        conn = get_db_connection()
        conn.execute('UPDATE orders SET status = "success" WHERE id = ?', (order_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    return jsonify({"success": False})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
