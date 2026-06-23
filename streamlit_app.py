import streamlit as st
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import io
import csv
import matplotlib
matplotlib.use('Agg')

# ---------- БАЗА ДАННЫХ ----------
def init_db():
    conn = sqlite3.connect('ratings.db')
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fio TEXT NOT NULL,
            group_name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS disciplines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            semester INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            discipline_id INTEGER NOT NULL,
            attendance REAL DEFAULT 0,
            assignments REAL DEFAULT 0,
            creativity REAL DEFAULT 0,
            exam REAL DEFAULT 0,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (discipline_id) REFERENCES disciplines(id) ON DELETE CASCADE,
            UNIQUE(student_id, discipline_id)
        );
    ''')
    try:
        c.execute('ALTER TABLE scores ADD COLUMN exam REAL DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE disciplines ADD COLUMN semester INTEGER DEFAULT 1')
    except:
        pass
    c.execute('UPDATE disciplines SET semester = 1 WHERE semester IS NULL')
    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect('ratings.db')

# ---------- ЛОГИКА ОЦЕНОК ----------
def calc_grade(total):
    if total >= 85: return 5
    elif total >= 70: return 4
    elif total >= 50: return 3
    else: return 2

def format_score(val):
    if val is None: return ''
    if val == int(val): return str(int(val))
    return f"{val:.2f}".rstrip('0').rstrip('.')

# ---------- ЗАГРУЗКА ДАННЫХ ----------
def load_students():
    conn = get_connection()
    df = pd.read_sql('SELECT id, fio, group_name FROM students ORDER BY group_name, fio', conn)
    conn.close()
    return df

def load_disciplines():
    conn = get_connection()
    df = pd.read_sql('SELECT id, name, semester FROM disciplines ORDER BY name', conn)
    conn.close()
    return df

def load_scores(student_id, semester=None):
    conn = get_connection()
    if semester is None:
        query = '''
            SELECT d.name, sc.attendance, sc.assignments, sc.creativity, sc.exam,
                   (sc.attendance + sc.assignments + sc.creativity + sc.exam) as total
            FROM scores sc
            JOIN disciplines d ON sc.discipline_id = d.id
            WHERE sc.student_id = ?
            ORDER BY d.name
        '''
        df = pd.read_sql(query, conn, params=(student_id,))
    else:
        query = '''
            SELECT d.name, sc.attendance, sc.assignments, sc.creativity, sc.exam,
                   (sc.attendance + sc.assignments + sc.creativity + sc.exam) as total
            FROM scores sc
            JOIN disciplines d ON sc.discipline_id = d.id
            WHERE sc.student_id = ? AND d.semester = ?
            ORDER BY d.name
        '''
        df = pd.read_sql(query, conn, params=(student_id, semester))
    conn.close()
    if not df.empty:
        df['grade'] = df['total'].apply(calc_grade)
        df.rename(columns={
            'name': 'Дисциплина',
            'attendance': 'Посещаемость',
            'assignments': 'Текущий и рубежный контроль',
            'creativity': 'Творческий рейтинг',
            'exam': 'Экзамен',
            'total': 'Итог',
            'grade': 'Оценка'
        }, inplace=True)
    return df

def load_ranking(semester):
    conn = get_connection()
    if semester is None:
        query = '''
            SELECT s.fio, s.group_name,
                   AVG(CASE
                        WHEN (sc.attendance + sc.assignments + sc.creativity + sc.exam) >= 85 THEN 5
                        WHEN (sc.attendance + sc.assignments + sc.creativity + sc.exam) >= 70 THEN 4
                        WHEN (sc.attendance + sc.assignments + sc.creativity + sc.exam) >= 50 THEN 3
                        ELSE 2
                       END) as avg_grade
            FROM students s
            LEFT JOIN scores sc ON s.id = sc.student_id
            GROUP BY s.id, s.fio, s.group_name
            ORDER BY avg_grade DESC, s.fio
        '''
    else:
        query = '''
            SELECT s.fio, s.group_name,
                   AVG(CASE
                        WHEN (sc.attendance + sc.assignments + sc.creativity + sc.exam) >= 85 THEN 5
                        WHEN (sc.attendance + sc.assignments + sc.creativity + sc.exam) >= 70 THEN 4
                        WHEN (sc.attendance + sc.assignments + sc.creativity + sc.exam) >= 50 THEN 3
                        ELSE 2
                       END) as avg_grade
            FROM students s
            JOIN scores sc ON s.id = sc.student_id
            JOIN disciplines d ON sc.discipline_id = d.id AND d.semester = ?
            GROUP BY s.id, s.fio, s.group_name
            ORDER BY avg_grade DESC, s.fio
        '''
    df = pd.read_sql(query, conn, params=(semester,) if semester is not None else None)
    conn.close()
    if not df.empty:
        df['Место'] = df['avg_grade'].rank(method='min', ascending=False).astype(int)
        df['Средний балл'] = df['avg_grade'].apply(format_score)
        df = df[['Место', 'fio', 'group_name', 'Средний балл']]
        df.rename(columns={'fio': 'ФИО', 'group_name': 'Группа'}, inplace=True)
    return df

def load_prev_ranking(semester):
    if semester is None or semester <= 1:
        return None
    prev_sem = semester - 1
    conn = get_connection()
    discs = pd.read_sql('SELECT COUNT(*) as cnt FROM disciplines WHERE semester = ?', conn, params=(prev_sem,))
    if discs['cnt'][0] == 0:
        conn.close()
        return None
    df = load_ranking(prev_sem)
    conn.close()
    return df

def get_semesters():
    conn = get_connection()
    semesters = pd.read_sql('SELECT DISTINCT semester FROM disciplines ORDER BY semester', conn)
    conn.close()
    return semesters['semester'].tolist()

# ---------- ОПЕРАЦИИ ----------
def add_student(fio, group):
    conn = get_connection()
    conn.execute('INSERT INTO students (fio, group_name) VALUES (?, ?)', (fio, group))
    conn.commit()
    conn.close()

def delete_student(student_id):
    conn = get_connection()
    conn.execute('DELETE FROM students WHERE id = ?', (student_id,))
    conn.commit()
    conn.close()

def add_discipline(name, semester):
    conn = get_connection()
    try:
        conn.execute('INSERT INTO disciplines (name, semester) VALUES (?, ?)', (name, semester))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def delete_discipline(disc_id):
    conn = get_connection()
    conn.execute('DELETE FROM disciplines WHERE id = ?', (disc_id,))
    conn.commit()
    conn.close()

def save_scores(student_id, disc_id, attendance, assignments, creativity, exam):
    conn = get_connection()
    cur = conn.execute('SELECT id FROM scores WHERE student_id=? AND discipline_id=?', (student_id, disc_id))
    if cur.fetchone():
        conn.execute('''UPDATE scores SET attendance=?, assignments=?, creativity=?, exam=?
                        WHERE student_id=? AND discipline_id=?''',
                     (attendance, assignments, creativity, exam, student_id, disc_id))
    else:
        conn.execute('''INSERT INTO scores (student_id, discipline_id, attendance, assignments, creativity, exam)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (student_id, disc_id, attendance, assignments, creativity, exam))
    conn.commit()
    conn.close()

def delete_score(student_id, disc_id):
    conn = get_connection()
    conn.execute('DELETE FROM scores WHERE student_id=? AND discipline_id=?', (student_id, disc_id))
    conn.commit()
    conn.close()

def get_discipline_id_by_name(name):
    conn = get_connection()
    cur = conn.execute('SELECT id FROM disciplines WHERE name=?', (name,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_student_info(student_id):
    conn = get_connection()
    cur = conn.execute('SELECT fio, group_name FROM students WHERE id=?', (student_id,))
    row = cur.fetchone()
    conn.close()
    return row

def export_csv(student_id, semester):
    scores_df = load_scores(student_id, semester)
    info = get_student_info(student_id)
    if info is None:
        return ""
    # Создаём строку с BOM для корректного отображения русских букв в Excel
    output = io.StringIO()
    output.write('\ufeff')          # <-- BOM
    writer = csv.writer(output)
    writer.writerow(['Студент', info[0], 'Группа', info[1]])
    if semester:
        writer.writerow([f'Семестр {semester}'])
    writer.writerow([])
    writer.writerow(['Дисциплина', 'Посещаемость (20)', 'Текущий и рубежный контроль (20)',
                     'Творческий рейтинг (20)', 'Экзамен (40)', 'Итог', 'Оценка'])
    for _, row in scores_df.iterrows():
        writer.writerow([row['Дисциплина'],
                         format_score(row['Посещаемость']),
                         format_score(row['Текущий и рубежный контроль']),
                         format_score(row['Творческий рейтинг']),
                         format_score(row['Экзамен']),
                         format_score(row['Итог']),
                         row['Оценка']])
    if len(scores_df) > 0:
        avg_total = scores_df['Итог'].astype(float).mean()
        avg_grade = scores_df['Оценка'].mean()
        writer.writerow([])
        writer.writerow(['Среднее', '', '', '', '', format_score(avg_total), format_score(avg_grade)])
    return output.getvalue()

# ---------- ИНИЦИАЛИЗАЦИЯ ----------
init_db()
st.set_page_config(page_title="Рейтинг студентов", layout="wide")
st.title("🎓 Балльно-рейтинговая система")

menu = st.sidebar.radio("Меню", ["Студенты", "Дисциплины", "Рейтинг"])

# ========== РАЗДЕЛ СТУДЕНТЫ ==========
if menu == "Студенты":
    st.header("Список студентов")
    with st.expander("➕ Добавить нового студента"):
        with st.form("add_student_form"):
            fio = st.text_input("ФИО")
            group = st.text_input("Группа")
            submitted = st.form_submit_button("Добавить")
            if submitted and fio and group:
                add_student(fio, group)
                st.success(f"Студент {fio} добавлен")
                st.rerun()

    students_df = load_students()
    if students_df.empty:
        st.info("Пока нет студентов. Добавьте первого!")
    else:
        student_options = {f"{row['fio']} ({row['group_name']})": row['id'] for _, row in students_df.iterrows()}
        selected_label = st.selectbox("Выберите студента", list(student_options.keys()))
        if selected_label:
            student_id = student_options[selected_label]
            info = get_student_info(student_id)
            if info is None:
                st.error("Студент не найден. Обновите страницу.")
            else:
                st.subheader(f"{info[0]} | Группа: {info[1]}")

                semesters = get_semesters()
                sem_options = ["Все семестры"] + [f"{s} семестр" for s in semesters]
                selected_sem = st.selectbox("Семестр", sem_options)
                semester = None if selected_sem == "Все семестры" else int(selected_sem.split()[0])

                scores_df = load_scores(student_id, semester)
                if not scores_df.empty:
                    # Создаём отображаемую копию с форматированием чисел (без .0)
                    display_df = scores_df.copy()
                    for col in ['Посещаемость', 'Текущий и рубежный контроль', 'Творческий рейтинг', 'Экзамен', 'Итог']:
                        display_df[col] = display_df[col].apply(format_score)
                    avg_grade = scores_df['Оценка'].astype(float).mean()
                    st.markdown(f"**Средняя оценка:** {format_score(avg_grade)} (дисциплин: {len(scores_df)})")
                    st.dataframe(display_df.style.map(
                        lambda x: 'color: green' if x == 5 else 'color: blue' if x == 4 else 'color: orange' if x == 3 else 'color: red',
                        subset=['Оценка']), hide_index=True)
                    csv_data = export_csv(student_id, semester)
                    st.download_button("📥 Скачать ведомость (CSV)", csv_data, f"student_{student_id}.csv", "text/csv")
                else:
                    st.info("Нет оценок по выбранному семестру")

                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("✏️ Добавить / изменить баллы"):
                        st.session_state['show_edit'] = True
                with col2:
                    if st.button("🗑️ Удалить баллы"):
                        st.session_state['show_delete'] = True
                with col3:
                    if st.button("📊 График успеваемости"):
                        st.session_state['show_graph'] = True

                if st.button("❌ Удалить студента"):
                    delete_student(student_id)
                    st.success("Студент удалён")
                    st.rerun()

                # ---------- БЛОК РЕДАКТИРОВАНИЯ / ДОБАВЛЕНИЯ ----------
                if st.session_state.get('show_edit', False):
                    available_discs = load_disciplines()
                    existing_names = scores_df['Дисциплина'].tolist() if not scores_df.empty else []
                    new_discs = available_discs[~available_discs['name'].isin(existing_names)]

                    action = st.radio("Действие", ["Добавить новую дисциплину", "Редактировать существующую"])
                    if action == "Редактировать существующую" and not existing_names:
                        st.warning("Нет оценок для редактирования")
                    elif action == "Добавить новую дисциплину" and new_discs.empty:
                        st.warning("Все дисциплины уже оценены")
                    else:
                        if action == "Редактировать существующую":
                            disc_name = st.selectbox("Выберите дисциплину", existing_names)
                            disc_id = get_discipline_id_by_name(disc_name)
                            cur = scores_df[scores_df['Дисциплина'] == disc_name].iloc[0]
                            with st.form("edit_scores_form"):
                                att = st.number_input("Посещаемость (0-20)", 0.0, 20.0, float(cur['Посещаемость']), step=0.5)
                                ass = st.number_input("Текущий и рубежный контроль (0-20)", 0.0, 20.0, float(cur['Текущий и рубежный контроль']), step=0.5)
                                cre = st.number_input("Творческий рейтинг (0-20)", 0.0, 20.0, float(cur['Творческий рейтинг']), step=0.5)
                                ex = st.number_input("Экзамен (0-40)", 0.0, 40.0, float(cur['Экзамен']), step=0.5)
                                if st.form_submit_button("Сохранить"):
                                    save_scores(student_id, disc_id, att, ass, cre, ex)
                                    st.success("Баллы обновлены")
                                    st.session_state['show_edit'] = False
                                    st.rerun()
                        else:
                            disc_name = st.selectbox("Выберите дисциплину", new_discs['name'])
                            disc_id = int(new_discs[new_discs['name'] == disc_name]['id'].values[0])
                            with st.form("add_scores_form"):
                                att = st.number_input("Посещаемость (0-20)", 0.0, 20.0, 0.0, step=0.5)
                                ass = st.number_input("Текущий и рубежный контроль (0-20)", 0.0, 20.0, 0.0, step=0.5)
                                cre = st.number_input("Творческий рейтинг (0-20)", 0.0, 20.0, 0.0, step=0.5)
                                ex = st.number_input("Экзамен (0-40)", 0.0, 40.0, 0.0, step=0.5)
                                if st.form_submit_button("Добавить"):
                                    save_scores(student_id, disc_id, att, ass, cre, ex)
                                    st.success("Баллы добавлены")
                                    st.session_state['show_edit'] = False
                                    st.rerun()
                    if st.button("Закрыть"):
                        st.session_state['show_edit'] = False
                        st.rerun()

                # ---------- УДАЛЕНИЕ БАЛЛОВ ----------
                if st.session_state.get('show_delete', False):
                    if not scores_df.empty:
                        disc_to_del = st.selectbox("Выберите дисциплину для удаления", scores_df['Дисциплина'])
                        if st.button("Удалить", key="confirm_delete"):
                            disc_id = get_discipline_id_by_name(disc_to_del)
                            delete_score(student_id, disc_id)
                            st.success(f"Баллы по дисциплине '{disc_to_del}' удалены")
                            st.session_state['show_delete'] = False
                            st.rerun()
                    else:
                        st.info("Нет баллов для удаления")
                    if st.button("Отмена"):
                        st.session_state['show_delete'] = False
                        st.rerun()

                # ---------- ГРАФИК УСПЕВАЕМОСТИ ----------
                if st.session_state.get('show_graph', False):
                    if not scores_df.empty:
                        fig, ax = plt.subplots(figsize=(10, 5))
                        disc_names = scores_df['Дисциплина']
                        x = range(len(disc_names))
                        w = 0.2
                        ax.bar([i - 1.5*w for i in x], scores_df['Посещаемость'], w, label='Посещаемость', color='#3498db')
                        ax.bar([i - 0.5*w for i in x], scores_df['Текущий и рубежный контроль'], w, label='Тек. и руб. контроль', color='#2ecc71')
                        ax.bar([i + 0.5*w for i in x], scores_df['Творческий рейтинг'], w, label='Творческий рейтинг', color='#f1c40f')
                        ax.bar([i + 1.5*w for i in x], scores_df['Экзамен'], w, label='Экзамен', color='#e74c3c')
                        ax.plot(x, scores_df['Итог'], 'k--o', label='Итог')
                        ax.set_xticks(x)
                        ax.set_xticklabels(disc_names, rotation=45, ha='right')
                        ax.legend()
                        ax.grid(axis='y', linestyle='--', alpha=0.7)
                        st.pyplot(fig)
                    else:
                        st.info("Нет данных для графика")
                    if st.button("Закрыть график"):
                        st.session_state['show_graph'] = False
                        st.rerun()

# ========== РАЗДЕЛ ДИСЦИПЛИНЫ ==========
elif menu == "Дисциплины":
    st.header("Управление дисциплинами")
    with st.expander("➕ Добавить дисциплину"):
        with st.form("add_disc_form"):
            name = st.text_input("Название дисциплины")
            semester = st.number_input("Семестр", min_value=1, step=1, value=1)
            if st.form_submit_button("Добавить"):
                if name:
                    if add_discipline(name, int(semester)):
                        st.success(f"Дисциплина '{name}' добавлена")
                        st.rerun()
                    else:
                        st.error("Такая дисциплина уже существует")
                else:
                    st.error("Введите название")

    discs_df = load_disciplines()
    if not discs_df.empty:
        st.dataframe(discs_df.rename(columns={'name': 'Название', 'semester': 'Семестр'}), hide_index=True)
        disc_to_del = st.selectbox("Выберите дисциплину для удаления", discs_df['name'])
        if st.button("Удалить дисциплину"):
            disc_id = discs_df[discs_df['name'] == disc_to_del]['id'].values[0]
            delete_discipline(int(disc_id))
            st.success("Дисциплина удалена")
            st.rerun()
    else:
        st.info("Нет дисциплин")

# ========== РАЗДЕЛ РЕЙТИНГ ==========
elif menu == "Рейтинг":
    st.header("Рейтинг студентов")
    semesters = get_semesters()
    sem_options = ["Все семестры"] + [f"{s} семестр" for s in semesters]
    selected_sem = st.selectbox("Семестр для рейтинга", sem_options)
    semester = None if selected_sem == "Все семестры" else int(selected_sem.split()[0])

    ranking_df = load_ranking(semester)
    if ranking_df.empty:
        st.info("Нет данных для рейтинга")
    else:
        prev_df = load_prev_ranking(semester)
        if prev_df is not None:
            prev_places = {(row['ФИО'], row['Группа']): (row['Место'], row['Средний балл']) for _, row in prev_df.iterrows()}
            changes = []
            delta_avgs = []
            for _, row in ranking_df.iterrows():
                key = (row['ФИО'], row['Группа'])
                if key in prev_places:
                    prev_place, prev_avg = prev_places[key]
                    diff = prev_place - row['Место']
                    changes.append(f"↑{diff}" if diff > 0 else f"↓{abs(diff)}" if diff < 0 else "–")
                    try:
                        delta = float(row['Средний балл']) - float(prev_avg)
                        delta_avgs.append(f"{'+' if delta > 0 else ''}{format_score(delta)}")
                    except:
                        delta_avgs.append("—")
                else:
                    changes.append("New")
                    delta_avgs.append("—")
            ranking_df['Δ Позиция'] = changes
            ranking_df['Δ Балл'] = delta_avgs
        else:
            ranking_df['Δ Позиция'] = "—"
            ranking_df['Δ Балл'] = "—"

        st.dataframe(ranking_df, hide_index=True)

        if st.button("📊 Построить график рейтинга"):
            fig, ax = plt.subplots(figsize=(10, 5))
            names = ranking_df['ФИО']
            avgs = [float(x) for x in ranking_df['Средний балл']]
            ax.bar(names, avgs, color='#3498db')
            mean_avg = sum(avgs) / len(avgs)
            ax.axhline(y=mean_avg, color='red', linestyle='--', label=f'Среднее по группе ({mean_avg:.2f})')
            for i, val in enumerate(avgs):
                ax.text(i, val + 0.05, f'{val:.2f}', ha='center')
            ax.set_xticklabels(names, rotation=45, ha='right')
            ax.legend()
            ax.grid(axis='y', linestyle='--', alpha=0.7)
            st.pyplot(fig)
