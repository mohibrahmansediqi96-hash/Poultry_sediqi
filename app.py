from flask import Flask, render_template, request, redirect, url_for, jsonify
import os, json
from datetime import datetime, date
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'sediqi_poultry_secret_2024'
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# PostgreSQL or SQLite fallback
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://poultry_db_autu_user:e3lE4HC6xCtgbyF3GFWxAPO5fu7Rtvdw@dpg-d8hurqgjo6nc73cmqoeg-a.oregon-postgres.render.com/poultry_db_autu')

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    # Render gives postgres:// but psycopg2 needs postgresql://
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    def get_db():
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    PH = '%s'  # PostgreSQL placeholder
    RETURNING = ' RETURNING id'
else:
    import sqlite3
    def get_db():
        db = sqlite3.connect('poultry_sediqi.db')
        db.row_factory = sqlite3.Row
        return db
    PH = '?'  # SQLite placeholder
    RETURNING = ''

def fetchone(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    if DATABASE_URL:
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))
    return dict(row)

def fetchall(cursor):
    rows = cursor.fetchall()
    if DATABASE_URL:
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, r)) for r in rows]
    return [dict(r) for r in rows]

ROSS_WEIGHT = {1:0.042,2:0.057,3:0.076,4:0.100,5:0.130,6:0.165,7:0.205,8:0.250,9:0.300,10:0.357,
               11:0.418,12:0.485,13:0.556,14:0.632,15:0.713,16:0.798,17:0.887,18:0.980,19:1.077,
               20:1.177,21:1.280,22:1.386,23:1.494,24:1.604,25:1.715,26:1.827,27:1.940,28:2.052,
               29:2.164,30:2.275,31:2.385,32:2.493,33:2.599,34:2.703,35:2.803,36:2.901,37:2.995,
               38:3.086,39:3.173,40:3.257,41:3.337,42:3.413}

ROSS_FEED = {1:13,2:17,3:22,4:27,5:33,6:40,7:47,8:55,9:63,10:72,11:81,12:91,13:101,14:112,
             15:123,16:134,17:145,18:157,19:169,20:181,21:193,22:205,23:217,24:229,25:241,
             26:253,27:265,28:277,29:289,30:300,31:311,32:322,33:333,34:343,35:352,36:361,
             37:370,38:378,39:386,40:393,41:400,42:406}

VACCINE_DAYS = [8, 14, 17, 24]

DISEASES = {
    'IB': {'name':'Infectious Bronchitis (IB)','symptoms':['سرفه','عطسه','ترشح بینی','کاهش تولید'],'drugs':'واکسن IB، آنتی‌بیوتیک ضد عفونت ثانویه، ویتامین C'},
    'ND': {'name':'Newcastle Disease (ND)','symptoms':['تنفسی','عصبی','اسهال سبز','مرگ ناگهانی','تلفات بالا'],'drugs':'واکسن ND لاسوتا، آنتی‌استرس، ویتامین E+Se'},
    'CRD': {'name':'Chronic Respiratory Disease','symptoms':['خس خس','ترشح چشم','ترشح بینی','کاهش رشد','سرفه'],'drugs':'Tylosin، Enrofloxacin، Doxycycline'},
    'Ascites': {'name':'Ascites - آب آوردگی','symptoms':['شکم برآمده','تنگی نفس','سیانوز','کبود تاج'],'drugs':'کاهش دان، ویتامین C، کاهش دما، Furosemide'},
    'Coccidiosis': {'name':'Coccidiosis - کوکسیدیوز','symptoms':['اسهال خونی','کاهش وزن','بی اشتهایی','مدفوع خونی'],'drugs':'Amprolium، Toltrazuril، Diclazuril'},
    'Ecoli': {'name':'E.coli - کلی باسیلوز','symptoms':['اسهال','ورم مفاصل','مرگ جوجه','ضعف'],'drugs':'Enrofloxacin، Colistin، Amoxicillin'},
    'NE': {'name':'Necrotic Enteritis','symptoms':['اسهال تیره','بی حالی','مرگ ناگهانی','روده آسیب دیده'],'drugs':'Bacitracin، Penicillin، Lincomycin'},
    'Gumboro': {'name':'Gumboro - IBD','symptoms':['اسهال سفید','بی حالی','لرزش','ضعف'],'drugs':'واکسن IBD، آنتی‌استرس، ویتامین A+D3+E'},
    'Marek': {'name':"Marek's Disease",'symptoms':['فلج پا','فلج بال','تومور','کاهش وزن شدید'],'drugs':'واکسن مارک، جداسازی بیمار، ویتامین B12'},
    'Mycoplasma': {'name':'Mycoplasmosis','symptoms':['ترشح بینی','ورم سینوس','کاهش تولید','سرفه مزمن'],'drugs':'Tylosin، Tilmicosin، Doxycycline'},
    'Fowl_Typhoid': {'name':'Fowl Typhoid','symptoms':['اسهال زرد','اسهال سبز','کاهش وزن','کم خونی'],'drugs':'Enrofloxacin، Amoxicillin، Chloramphenicol'},
    'Hypoglycemia': {'name':'Hypoglycemia - افت قند','symptoms':['ضعف','لرزش','کما','افت ناگهانی'],'drugs':'آب قند، گلوکز خوراکی، گرم کردن'}
}

def suggest_disease(symptoms_text):
    symptoms_text = symptoms_text.lower()
    scores = {}
    for key, d in DISEASES.items():
        score = sum(1 for sym in d['symptoms'] if any(w in symptoms_text for w in sym.lower().split()))
        if score > 0:
            scores[key] = score
    return [{'key':k,'name':DISEASES[k]['name'],'drugs':DISEASES[k]['drugs'],'score':s}
            for k,s in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]]

def init_db():
    conn = get_db()
    cur = conn.cursor()
    if DATABASE_URL:
        cur.execute('''CREATE TABLE IF NOT EXISTS flocks (
            id SERIAL PRIMARY KEY, entry_date TEXT NOT NULL, count INTEGER NOT NULL,
            price_per_chick REAL NOT NULL, breed TEXT DEFAULT 'Ross',
            status TEXT DEFAULT 'active', created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS daily_records (
            id SERIAL PRIMARY KEY, flock_id INTEGER, record_date TEXT NOT NULL,
            day_number INTEGER, mortality INTEGER DEFAULT 0, feed_consumed REAL DEFAULT 0,
            water_consumed REAL DEFAULT 0, notes TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS weight_records (
            id SERIAL PRIMARY KEY, flock_id INTEGER, record_date TEXT NOT NULL,
            week_number INTEGER, avg_weight REAL, sample_count INTEGER DEFAULT 50, notes TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY, flock_id INTEGER, expense_date TEXT NOT NULL,
            category TEXT NOT NULL, amount REAL NOT NULL, description TEXT, receipt_image TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS sales (
            id SERIAL PRIMARY KEY, flock_id INTEGER, sale_date TEXT NOT NULL,
            customer_name TEXT NOT NULL, quantity INTEGER NOT NULL, total_weight REAL NOT NULL,
            price_per_kg REAL NOT NULL, total_amount REAL NOT NULL,
            receipt_paid INTEGER DEFAULT 0, notes TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS health_records (
            id SERIAL PRIMARY KEY, flock_id INTEGER, record_date TEXT NOT NULL,
            disease_key TEXT, symptoms TEXT, recommended_drugs TEXT,
            used_drug TEXT, resolved INTEGER DEFAULT 0, notes TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS vaccine_records (
            id SERIAL PRIMARY KEY, flock_id INTEGER, vaccine_day INTEGER,
            vaccine_name TEXT, vaccine_date TEXT, done INTEGER DEFAULT 0, notes TEXT)''')
    else:
        cur.executescript('''
            CREATE TABLE IF NOT EXISTS flocks (id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL, count INTEGER NOT NULL, price_per_chick REAL NOT NULL,
                breed TEXT DEFAULT 'Ross', status TEXT DEFAULT 'active', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS daily_records (id INTEGER PRIMARY KEY AUTOINCREMENT,
                flock_id INTEGER, record_date TEXT NOT NULL, day_number INTEGER,
                mortality INTEGER DEFAULT 0, feed_consumed REAL DEFAULT 0,
                water_consumed REAL DEFAULT 0, notes TEXT);
            CREATE TABLE IF NOT EXISTS weight_records (id INTEGER PRIMARY KEY AUTOINCREMENT,
                flock_id INTEGER, record_date TEXT NOT NULL, week_number INTEGER,
                avg_weight REAL, sample_count INTEGER DEFAULT 50, notes TEXT);
            CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT,
                flock_id INTEGER, expense_date TEXT NOT NULL, category TEXT NOT NULL,
                amount REAL NOT NULL, description TEXT, receipt_image TEXT);
            CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY AUTOINCREMENT,
                flock_id INTEGER, sale_date TEXT NOT NULL, customer_name TEXT NOT NULL,
                quantity INTEGER NOT NULL, total_weight REAL NOT NULL, price_per_kg REAL NOT NULL,
                total_amount REAL NOT NULL, receipt_paid INTEGER DEFAULT 0, notes TEXT);
            CREATE TABLE IF NOT EXISTS health_records (id INTEGER PRIMARY KEY AUTOINCREMENT,
                flock_id INTEGER, record_date TEXT NOT NULL, disease_key TEXT,
                symptoms TEXT, recommended_drugs TEXT, used_drug TEXT,
                resolved INTEGER DEFAULT 0, notes TEXT);
            CREATE TABLE IF NOT EXISTS vaccine_records (id INTEGER PRIMARY KEY AUTOINCREMENT,
                flock_id INTEGER, vaccine_day INTEGER, vaccine_name TEXT,
                vaccine_date TEXT, done INTEGER DEFAULT 0, notes TEXT);
        ''')
    conn.commit()
    cur.close()
    conn.close()

def allowed_file(f): return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_day(entry_date_str, target_date_str=None):
    entry = datetime.strptime(entry_date_str, '%Y-%m-%d').date()
    target = date.today() if not target_date_str else datetime.strptime(target_date_str, '%Y-%m-%d').date()
    return (target - entry).days + 1

def q(sql):
    """Replace ? with %s for PostgreSQL"""
    return sql.replace('?', PH) if DATABASE_URL else sql

def last_id(cur, table='flocks'):
    if DATABASE_URL:
        return cur.fetchone()[0]
    return cur.lastrowid

def get_flock_summary(flock_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(q('SELECT * FROM flocks WHERE id=?'), (flock_id,))
    flock = fetchone(cur)
    if not flock:
        cur.close(); conn.close(); return None
    day = calculate_day(flock['entry_date'])
    cur.execute(q('SELECT COALESCE(SUM(mortality),0) as m FROM daily_records WHERE flock_id=?'), (flock_id,))
    total_mortality = fetchone(cur)['m']
    current_count = flock['count'] - total_mortality
    mortality_rate = (total_mortality / flock['count'] * 100) if flock['count'] > 0 else 0
    cur.execute(q('SELECT COALESCE(SUM(feed_consumed),0) as f FROM daily_records WHERE flock_id=?'), (flock_id,))
    total_feed = fetchone(cur)['f']
    cur.execute(q('SELECT avg_weight FROM weight_records WHERE flock_id=? ORDER BY week_number DESC LIMIT 1'), (flock_id,))
    lw = fetchone(cur)
    avg_weight = lw['avg_weight'] if lw else 0
    std_weight = ROSS_WEIGHT.get(min(day,42), ROSS_WEIGHT[42])
    std_feed = ROSS_FEED.get(min(day,42), ROSS_FEED[42])
    total_weight_gain = avg_weight * current_count if avg_weight > 0 else 0
    fcr = (total_feed / total_weight_gain) if total_weight_gain > 0 else 0
    cur.execute(q('SELECT COALESCE(SUM(amount),0) as e FROM expenses WHERE flock_id=?'), (flock_id,))
    total_expenses = fetchone(cur)['e']
    expense_per_bird = (total_expenses / current_count) if current_count > 0 else 0
    cur.execute(q('SELECT * FROM sales WHERE flock_id=?'), (flock_id,))
    sales = fetchall(cur)
    total_sold = sum(s['quantity'] for s in sales)
    total_revenue = sum(s['total_amount'] for s in sales)
    total_weight_sold = sum(s['total_weight'] for s in sales)
    purchase_cost = flock['count'] * flock['price_per_chick']
    total_cost = purchase_cost + total_expenses
    profit_loss = total_revenue - total_cost
    epd = 0
    if avg_weight > 0 and day > 0 and flock['count'] > 0 and fcr > 0:
        livability = ((flock['count'] - total_mortality) / flock['count']) * 100
        epd = (avg_weight * livability * (100/fcr)) / (day * 10)
    vaccine_alerts = []
    for vday in VACCINE_DAYS:
        if abs(day - vday) <= 1:
            cur.execute(q('SELECT done FROM vaccine_records WHERE flock_id=? AND vaccine_day=?'), (flock_id, vday))
            done = fetchone(cur)
            if not done or not done['done']:
                vaccine_alerts.append(vday)
    cur.close(); conn.close()
    return {
        'flock': flock, 'day': day, 'current_count': current_count,
        'total_mortality': total_mortality, 'mortality_rate': round(mortality_rate,2),
        'total_feed': round(total_feed,2), 'avg_weight': round(avg_weight,3),
        'std_weight': std_weight, 'std_feed': std_feed, 'fcr': round(fcr,3), 'std_fcr': 1.65,
        'total_expenses': round(total_expenses,2), 'expense_per_bird': round(expense_per_bird,2),
        'total_sold': total_sold, 'total_revenue': round(total_revenue,2),
        'total_weight_sold': round(total_weight_sold,2), 'profit_loss': round(profit_loss,2),
        'epd': round(epd,2), 'vaccine_alerts': vaccine_alerts,
        'purchase_cost': round(purchase_cost,2), 'total_cost': round(total_cost,2)
    }

@app.route('/')
def index(): return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT * FROM flocks ORDER BY entry_date DESC')
    flocks = fetchall(cur)
    cur.close(); conn.close()
    summaries = [s for f in flocks for s in [get_flock_summary(f['id'])] if s]
    return render_template('dashboard.html', summaries=summaries)

@app.route('/flock/new', methods=['GET','POST'])
def new_flock():
    if request.method == 'POST':
        conn = get_db(); cur = conn.cursor()
        if DATABASE_URL:
            cur.execute(q('INSERT INTO flocks (entry_date,count,price_per_chick,breed) VALUES (?,?,?,?) RETURNING id'),
                       (request.form['entry_date'],request.form['count'],request.form['price_per_chick'],request.form.get('breed','Ross')))
            flock_id = cur.fetchone()[0]
        else:
            cur.execute(q('INSERT INTO flocks (entry_date,count,price_per_chick,breed) VALUES (?,?,?,?)'),
                       (request.form['entry_date'],request.form['count'],request.form['price_per_chick'],request.form.get('breed','Ross')))
            flock_id = cur.lastrowid
        vaccine_names = {8:'IB+ND (اسپری)',14:'IBD Gumboro',17:'ND لاسوتا',24:'IBD تقویتی'}
        for vday in VACCINE_DAYS:
            cur.execute(q('INSERT INTO vaccine_records (flock_id,vaccine_day,vaccine_name) VALUES (?,?,?)'),
                       (flock_id, vday, vaccine_names.get(vday,'واکسن')))
        conn.commit(); cur.close(); conn.close()
        return redirect(url_for('flock_detail', flock_id=flock_id))
    return render_template('new_flock.html')

@app.route('/flock/<int:flock_id>')
def flock_detail(flock_id):
    summary = get_flock_summary(flock_id)
    if not summary: return redirect(url_for('dashboard'))
    conn = get_db(); cur = conn.cursor()
    cur.execute(q('SELECT * FROM daily_records WHERE flock_id=? ORDER BY record_date DESC LIMIT 30'), (flock_id,))
    daily_records = fetchall(cur)
    cur.execute(q('SELECT * FROM weight_records WHERE flock_id=? ORDER BY week_number'), (flock_id,))
    weight_records = fetchall(cur)
    cur.execute(q('SELECT * FROM expenses WHERE flock_id=? ORDER BY expense_date DESC'), (flock_id,))
    expenses = fetchall(cur)
    cur.execute(q('SELECT * FROM sales WHERE flock_id=? ORDER BY sale_date DESC'), (flock_id,))
    sales = fetchall(cur)
    cur.execute(q('SELECT * FROM health_records WHERE flock_id=? AND resolved=0 ORDER BY record_date DESC'), (flock_id,))
    health_records = fetchall(cur)
    cur.execute(q('SELECT * FROM health_records WHERE flock_id=? AND resolved=1 ORDER BY record_date DESC LIMIT 10'), (flock_id,))
    resolved_records = fetchall(cur)
    cur.execute(q('SELECT * FROM vaccine_records WHERE flock_id=? ORDER BY vaccine_day'), (flock_id,))
    vaccines = fetchall(cur)
    cur.close(); conn.close()
    weight_chart = {'labels':[],'actual':[],'standard':[]}
    for w in weight_records:
        weight_chart['labels'].append(f'Week {w["week_number"]}')
        weight_chart['actual'].append(w['avg_weight'])
        weight_chart['standard'].append(ROSS_WEIGHT.get(min(w['week_number']*7,42), ROSS_WEIGHT[42]))
    customer_summary = {}
    for s in sales:
        cn = s['customer_name']
        if cn not in customer_summary:
            customer_summary[cn] = {'quantity':0,'total_weight':0.0,'total_amount':0.0,'paid':0.0,'unpaid':0.0}
        customer_summary[cn]['quantity'] += s['quantity']
        customer_summary[cn]['total_weight'] += s['total_weight']
        customer_summary[cn]['total_amount'] += s['total_amount']
        if s['receipt_paid']:
            customer_summary[cn]['paid'] += s['total_amount']
        else:
            customer_summary[cn]['unpaid'] += s['total_amount']
    return render_template('flock_detail.html',
        summary=summary, daily_records=daily_records, weight_records=weight_records,
        expenses=expenses, sales=sales, health_records=health_records,
        resolved_records=resolved_records, vaccines=vaccines,
        weight_chart=json.dumps(weight_chart),
        customer_summary=customer_summary, diseases=DISEASES,
        ross_weight=ROSS_WEIGHT, ross_feed=ROSS_FEED)

@app.route('/flock/<int:flock_id>/daily', methods=['POST'])
def add_daily(flock_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute(q('SELECT entry_date FROM flocks WHERE id=?'), (flock_id,))
    flock = fetchone(cur)
    day = calculate_day(flock['entry_date'], request.form['record_date'])
    cur.execute(q('INSERT INTO daily_records (flock_id,record_date,day_number,mortality,feed_consumed,water_consumed,notes) VALUES (?,?,?,?,?,?,?)'),
               (flock_id,request.form['record_date'],day,request.form.get('mortality',0),
                request.form.get('feed_consumed',0),request.form.get('water_consumed',0),request.form.get('notes','')))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for('flock_detail', flock_id=flock_id))

@app.route('/flock/<int:flock_id>/weight', methods=['POST'])
def add_weight(flock_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute(q('INSERT INTO weight_records (flock_id,record_date,week_number,avg_weight,sample_count,notes) VALUES (?,?,?,?,?,?)'),
               (flock_id,request.form['record_date'],request.form['week_number'],
                request.form['avg_weight'],request.form.get('sample_count',50),request.form.get('notes','')))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for('flock_detail', flock_id=flock_id))

@app.route('/flock/<int:flock_id>/expense', methods=['POST'])
def add_expense(flock_id):
    receipt_image = None
    if 'receipt_image' in request.files:
        file = request.files['receipt_image']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(f"{flock_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            receipt_image = filename
    conn = get_db(); cur = conn.cursor()
    cur.execute(q('INSERT INTO expenses (flock_id,expense_date,category,amount,description,receipt_image) VALUES (?,?,?,?,?,?)'),
               (flock_id,request.form['expense_date'],request.form['category'],
                request.form['amount'],request.form.get('description',''),receipt_image))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for('flock_detail', flock_id=flock_id))

@app.route('/flock/<int:flock_id>/sale', methods=['POST'])
def add_sale(flock_id):
    tw = float(request.form['total_weight']); pkg = float(request.form['price_per_kg'])
    conn = get_db(); cur = conn.cursor()
    cur.execute(q('INSERT INTO sales (flock_id,sale_date,customer_name,quantity,total_weight,price_per_kg,total_amount,receipt_paid,notes) VALUES (?,?,?,?,?,?,?,?,?)'),
               (flock_id,request.form['sale_date'],request.form['customer_name'],
                request.form['quantity'],tw,pkg,tw*pkg,
                1 if request.form.get('receipt_paid') else 0,request.form.get('notes','')))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for('flock_detail', flock_id=flock_id))

@app.route('/sale/<int:sale_id>/toggle_payment', methods=['POST'])
def toggle_payment(sale_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute(q('SELECT receipt_paid FROM sales WHERE id=?'), (sale_id,))
    sale = fetchone(cur)
    new_status = 0 if sale['receipt_paid'] else 1
    cur.execute(q('UPDATE sales SET receipt_paid=? WHERE id=?'), (new_status, sale_id))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'paid': new_status})

@app.route('/flock/<int:flock_id>/health', methods=['POST'])
def add_health(flock_id):
    dk = request.form.get('disease_key','')
    symptoms = request.form.get('symptoms','')
    recommended = request.form.get('recommended_drugs','')
    if dk and dk in DISEASES:
        symptoms = symptoms or ', '.join(DISEASES[dk]['symptoms'])
        recommended = recommended or DISEASES[dk]['drugs']
    conn = get_db(); cur = conn.cursor()
    cur.execute(q('INSERT INTO health_records (flock_id,record_date,disease_key,symptoms,recommended_drugs,used_drug) VALUES (?,?,?,?,?,?)'),
               (flock_id,request.form['record_date'],dk,symptoms,recommended,request.form.get('used_drug','')))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for('flock_detail', flock_id=flock_id))

@app.route('/health/<int:record_id>/use_drug', methods=['POST'])
def use_drug(record_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute(q('SELECT flock_id FROM health_records WHERE id=?'), (record_id,))
    rec = fetchone(cur)
    cur.execute(q('UPDATE health_records SET used_drug=?, resolved=1 WHERE id=?'),
               (request.form.get('used_drug',''), record_id))
    conn.commit(); flock_id = rec['flock_id']; cur.close(); conn.close()
    return redirect(url_for('flock_detail', flock_id=flock_id))

@app.route('/health/<int:record_id>/delete', methods=['POST'])
def delete_health(record_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute(q('SELECT flock_id FROM health_records WHERE id=?'), (record_id,))
    rec = fetchone(cur); flock_id = rec['flock_id']
    cur.execute(q('DELETE FROM health_records WHERE id=?'), (record_id,))
    conn.commit(); cur.close(); conn.close()
    return redirect(url_for('flock_detail', flock_id=flock_id))

@app.route('/vaccine/<int:vaccine_id>/done', methods=['POST'])
def mark_vaccine_done(vaccine_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute(q('SELECT flock_id FROM vaccine_records WHERE id=?'), (vaccine_id,))
    rec = fetchone(cur)
    cur.execute(q('UPDATE vaccine_records SET done=1, vaccine_date=?, notes=? WHERE id=?'),
               (date.today().isoformat(), request.form.get('notes',''), vaccine_id))
    conn.commit(); flock_id = rec['flock_id']; cur.close(); conn.close()
    return redirect(url_for('flock_detail', flock_id=flock_id))

@app.route('/api/suggest_disease', methods=['POST'])
def api_suggest_disease():
    symptoms = request.json.get('symptoms','')
    return jsonify(suggest_disease(symptoms))

@app.route('/api/disease/<key>')
def api_disease(key):
    if key in DISEASES: return jsonify(DISEASES[key])
    return jsonify({}), 404

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)

# patch: auto init
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
except Exception as e:
    print(f"DB init ERROR: {e}", flush=True)
