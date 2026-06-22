import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import csv

# Для графиков
import matplotlib
matplotlib.use('TkAgg')  # Важно для встраивания в Tkinter
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ============ БАЗА ДАННЫХ ============
class Database:
    def __init__(self, db_name='ratings.db'):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fio TEXT NOT NULL,
                group_name TEXT NOT NULL
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS disciplines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                semester INTEGER DEFAULT 1
            )
        ''')
        self.cursor.execute('''
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
            )
        ''')

        try:
            self.cursor.execute('ALTER TABLE scores ADD COLUMN exam REAL DEFAULT 0')
        except sqlite3.OperationalError:
            pass
        try:
            self.cursor.execute('ALTER TABLE disciplines ADD COLUMN semester INTEGER DEFAULT 1')
        except sqlite3.OperationalError:
            pass
        self.cursor.execute('UPDATE disciplines SET semester = 1 WHERE semester IS NULL')
        self.conn.commit()

    # ===== СТУДЕНТЫ =====
    def add_student(self, fio, group_name):
        try:
            self.cursor.execute('INSERT INTO students (fio, group_name) VALUES (?, ?)', (fio, group_name))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            messagebox.showerror("Ошибка БД", str(e))
            return False

    def get_all_students(self):
        self.cursor.execute('SELECT id, fio, group_name FROM students ORDER BY group_name, fio')
        return self.cursor.fetchall()

    def delete_student(self, student_id):
        self.cursor.execute('DELETE FROM students WHERE id = ?', (student_id,))
        self.conn.commit()

    def get_student_info(self, student_id):
        self.cursor.execute('SELECT fio, group_name FROM students WHERE id=?', (student_id,))
        return self.cursor.fetchone()

    # ===== ДИСЦИПЛИНЫ =====
    def add_discipline(self, name, semester):
        try:
            self.cursor.execute('INSERT INTO disciplines (name, semester) VALUES (?, ?)', (name, semester))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            messagebox.showwarning("Предупреждение", "Дисциплина уже существует")
            return False

    def get_all_disciplines(self):
        self.cursor.execute('SELECT id, name, semester FROM disciplines ORDER BY name')
        return self.cursor.fetchall()

    def delete_discipline(self, disc_id):
        self.cursor.execute('DELETE FROM disciplines WHERE id = ?', (disc_id,))
        self.conn.commit()

    def get_semesters(self):
        self.cursor.execute('SELECT DISTINCT semester FROM disciplines ORDER BY semester')
        return [row[0] for row in self.cursor.fetchall()]

    def count_disciplines_in_semester(self, semester):
        if semester is None:
            self.cursor.execute('SELECT COUNT(*) FROM disciplines')
        else:
            self.cursor.execute('SELECT COUNT(*) FROM disciplines WHERE semester=?', (semester,))
        return self.cursor.fetchone()[0]

    # ===== ОЦЕНКИ =====
    def save_scores(self, student_id, disc_id, attendance, assignments, creativity, exam):
        self.cursor.execute('SELECT id FROM scores WHERE student_id=? AND discipline_id=?', (student_id, disc_id))
        exist = self.cursor.fetchone()
        if exist:
            self.cursor.execute('''
                UPDATE scores SET attendance=?, assignments=?, creativity=?, exam=?
                WHERE student_id=? AND discipline_id=?
            ''', (attendance, assignments, creativity, exam, student_id, disc_id))
        else:
            self.cursor.execute('''
                INSERT INTO scores (student_id, discipline_id, attendance, assignments, creativity, exam)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (student_id, disc_id, attendance, assignments, creativity, exam))
        self.conn.commit()
        return True

    def delete_score(self, student_id, disc_id):
        self.cursor.execute('DELETE FROM scores WHERE student_id=? AND discipline_id=?', (student_id, disc_id))
        self.conn.commit()

    def get_scores_for_student(self, student_id, semester=None):
        if semester is None:
            query = '''
                SELECT d.name, sc.attendance, sc.assignments, sc.creativity, sc.exam,
                       (sc.attendance + sc.assignments + sc.creativity + sc.exam) as total
                FROM scores sc
                JOIN disciplines d ON sc.discipline_id = d.id
                WHERE sc.student_id = ?
                ORDER BY d.name
            '''
            self.cursor.execute(query, (student_id,))
        else:
            query = '''
                SELECT d.name, sc.attendance, sc.assignments, sc.creativity, sc.exam,
                       (sc.attendance + sc.assignments + sc.creativity + sc.exam) as total
                FROM scores sc
                JOIN disciplines d ON sc.discipline_id = d.id
                WHERE sc.student_id = ? AND d.semester = ?
                ORDER BY d.name
            '''
            self.cursor.execute(query, (student_id, semester))
        return self.cursor.fetchall()

    def get_student_avg_for_semester(self, student_id, semester):
        scores = self.get_scores_for_student(student_id, semester)
        if not scores:
            return None
        grade_sum = sum(self._calc_grade_for_total(total) for _, _, _, _, _, total in scores)
        return grade_sum / len(scores)

    def get_students_ranking(self, semester):
        self.cursor.execute('SELECT id, fio, group_name FROM students')
        students = self.cursor.fetchall()
        result = []
        for sid, fio, group in students:
            avg = self.get_student_avg_for_semester(sid, semester)
            if avg is not None:
                result.append((sid, fio, group, avg))
        result.sort(key=lambda x: (-x[3], x[1]))
        ranked = []
        rank = 1
        prev_avg = None
        for i, (sid, fio, group, avg) in enumerate(result):
            if i == 0:
                current_rank = 1
                prev_avg = avg
            else:
                if avg == prev_avg:
                    current_rank = rank
                else:
                    rank = i + 1
                    current_rank = rank
                    prev_avg = avg
            ranked.append((sid, fio, group, avg, current_rank))
        return ranked

    def get_all_students_with_avg_grade(self, semester=None):
        self.cursor.execute('SELECT id, fio, group_name FROM students')
        students = self.cursor.fetchall()
        result = []
        for sid, fio, group in students:
            scores = self.get_scores_for_student(sid, semester)
            if not scores:
                avg = 0.0
            else:
                grade_sum = sum(self._calc_grade_for_total(total) for _, _, _, _, _, total in scores)
                avg = grade_sum / len(scores)
            result.append((fio, group, avg))
        result.sort(key=lambda x: (-x[2], x[0]))
        return result

    @staticmethod
    def _calc_grade_for_total(total):
        if total >= 85:
            return 5
        elif total >= 70:
            return 4
        elif total >= 50:
            return 3
        else:
            return 2

    def get_disciplines_not_for_student(self, student_id, semester=None):
        if semester is None:
            query = '''
                SELECT id, name FROM disciplines
                WHERE id NOT IN (
                    SELECT discipline_id FROM scores WHERE student_id = ?
                )
                ORDER BY name
            '''
            self.cursor.execute(query, (student_id,))
        else:
            query = '''
                SELECT id, name FROM disciplines
                WHERE semester = ? AND id NOT IN (
                    SELECT discipline_id FROM scores WHERE student_id = ?
                )
                ORDER BY name
            '''
            self.cursor.execute(query, (semester, student_id))
        return self.cursor.fetchall()

    def close(self):
        self.conn.close()

# ============ ГЛАВНОЕ ПРИЛОЖЕНИЕ ============
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Рейтинг студентов")
        self.geometry("1000x620")
        self.configure(bg='#f0f4f8')

        self.style = ttk.Style()
        self.style.theme_use('clam')

        self.bg_color = '#f0f4f8'
        self.header_color = '#1e3a5f'
        self.accent_color = '#2e86c1'
        self.button_color = '#2e86c1'
        self.button_hover = '#1f618d'
        self.grade_colors = {5: '#27ae60', 4: '#2980b9', 3: '#f39c12', 2: '#e74c3c'}

        self.style.configure('TFrame', background=self.bg_color)
        self.style.configure('TLabel', background=self.bg_color, font=('Segoe UI', 10))
        self.style.configure('Header.TLabel', font=('Segoe UI', 12, 'bold'), foreground='white', background=self.header_color)
        self.style.configure('StudentInfo.TLabel', font=('Segoe UI', 11, 'bold'), background='white')
        self.style.configure('Avg.TLabel', font=('Segoe UI', 10, 'italic'), background='white')
        self.style.configure('TButton', font=('Segoe UI', 9), borderwidth=0, relief='flat', padding=6)
        self.style.map('TButton',
                       background=[('active', self.button_hover), ('!active', self.button_color)],
                       foreground=[('active', 'white'), ('!active', 'white')])
        self.style.configure('Treeview', font=('Segoe UI', 9), rowheight=25, background='white',
                             fieldbackground='#f9fbfd', borderwidth=1)
        self.style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'), background=self.header_color,
                             foreground='white', relief='flat')

        self.db = Database()
        self.current_student_id = None
        self.current_semester = None

        self.create_widgets()
        self.refresh_student_list()
        self.refresh_semester_selector()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    @staticmethod
    def format_score(value):
        if value == int(value):
            return str(int(value))
        return f"{value:.2f}".rstrip('0').rstrip('.')

    def create_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ---- ЛЕВАЯ ПАНЕЛЬ (студенты) ----
        left_frame = ttk.Frame(main_frame, width=260)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_frame.pack_propagate(False)

        header_students = tk.Label(left_frame, text="СТУДЕНТЫ", font=('Segoe UI', 12, 'bold'),
                                   bg=self.header_color, fg='white', pady=8)
        header_students.pack(fill=tk.X)

        list_container = tk.Frame(left_frame, bg='white', highlightbackground='#d5d8dc', highlightthickness=1)
        list_container.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.student_listbox = tk.Listbox(list_container, width=30, height=18, font=('Segoe UI', 10),
                                          bg='white', selectbackground=self.accent_color,
                                          selectforeground='white', borderwidth=0, highlightthickness=0)
        self.student_listbox.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.student_listbox.bind('<<ListboxSelect>>', self.on_student_select)

        btn_frame_left = ttk.Frame(left_frame)
        btn_frame_left.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_frame_left, text="+ Добавить студента", command=self.add_student_dialog).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame_left, text="– Удалить студента", command=self.delete_student).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame_left, text="Управление дисциплинами", command=self.open_discipline_manager).pack(fill=tk.X, pady=2)

        # ---- ПРАВАЯ ПАНЕЛЬ (успеваемость) ----
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        info_container = tk.Frame(right_frame, bg='white', highlightbackground='#d5d8dc', highlightthickness=1)
        info_container.pack(fill=tk.X, pady=(0, 10))

        self.student_info_label = tk.Label(info_container, text="Выберите студента",
                                           font=('Segoe UI', 14, 'bold'), bg='white', fg=self.header_color,
                                           pady=10, padx=15)
        self.student_info_label.pack(side=tk.LEFT)

        sem_frame = tk.Frame(info_container, bg='white')
        sem_frame.pack(side=tk.RIGHT, padx=15, pady=10)
        tk.Label(sem_frame, text="Семестр:", bg='white', font=('Segoe UI', 10)).pack(side=tk.LEFT)
        self.semester_combo = ttk.Combobox(sem_frame, state='readonly', width=15)
        self.semester_combo.pack(side=tk.LEFT, padx=5)
        self.semester_combo.bind('<<ComboboxSelected>>', self.on_semester_changed)

        # Таблица оценок
        table_container = tk.Frame(right_frame, bg='white', highlightbackground='#d5d8dc', highlightthickness=1)
        table_container.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        columns = ('discipline', 'attendance', 'assignments', 'creativity', 'exam', 'total', 'grade')
        self.tree = ttk.Treeview(table_container, columns=columns, show='headings', height=10)
        self.tree.heading('discipline', text='Дисциплина')
        self.tree.heading('attendance', text='Посещаемость (20)')
        self.tree.heading('assignments', text='Текущий и рубежный контроль (20)')
        self.tree.heading('creativity', text='Творческий рейтинг (20)')
        self.tree.heading('exam', text='Экзамен (40)')
        self.tree.heading('total', text='Итог')
        self.tree.heading('grade', text='Оценка')

        self.tree.column('discipline', width=160, anchor=tk.W)
        self.tree.column('attendance', width=100, anchor=tk.CENTER)
        self.tree.column('assignments', width=100, anchor=tk.CENTER)
        self.tree.column('creativity', width=100, anchor=tk.CENTER)
        self.tree.column('exam', width=80, anchor=tk.CENTER)
        self.tree.column('total', width=70, anchor=tk.CENTER)
        self.tree.column('grade', width=70, anchor=tk.CENTER)

        scrollbar_y = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)

        for grade_value, color in self.grade_colors.items():
            self.tree.tag_configure(f'grade_{grade_value}', foreground=color, font=('Segoe UI', 9, 'bold'))

        # Средний балл
        avg_frame = tk.Frame(right_frame, bg='white', highlightbackground='#d5d8dc', highlightthickness=1)
        avg_frame.pack(fill=tk.X, pady=(0, 10))

        self.avg_label = tk.Label(avg_frame, text="Средний балл: ---",
                                  font=('Segoe UI', 11, 'italic'), bg='white', fg=self.header_color,
                                  pady=8, padx=15)
        self.avg_label.pack(anchor=tk.W)

        # Кнопки действий
        btn_frame_right = ttk.Frame(right_frame)
        btn_frame_right.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_frame_right, text="Добавить / изменить баллы", command=self.add_edit_scores).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame_right, text="Удалить баллы", command=self.delete_score).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame_right, text="Экспорт ведомости", command=self.export_student_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame_right, text="Рейтинг студентов", command=self.show_rating).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame_right, text="📊 График", command=self.show_student_graph).pack(side=tk.LEFT, padx=2)

    # ---------- Семестры ----------
    def refresh_semester_selector(self):
        semesters = self.db.get_semesters()
        values = ["Все семестры"] + [f"{s} семестр" for s in semesters]
        self.semester_combo['values'] = values
        if self.current_semester is None:
            self.semester_combo.current(0)
        else:
            try:
                idx = values.index(f"{self.current_semester} семестр")
                self.semester_combo.current(idx)
            except ValueError:
                self.semester_combo.current(0)
                self.current_semester = None

    def on_semester_changed(self, event):
        sel = self.semester_combo.get()
        if sel == "Все семестры":
            self.current_semester = None
        else:
            num = int(sel.split()[0])
            self.current_semester = num
        if self.current_student_id is not None:
            self.load_student_data()

    # ---------- Студенты и таблица ----------
    def refresh_student_list(self):
        self.student_listbox.delete(0, tk.END)
        students = self.db.get_all_students()
        self.student_ids = [s[0] for s in students]
        for s in students:
            self.student_listbox.insert(tk.END, f"{s[1]} ({s[2]})")

    def on_student_select(self, event):
        selection = self.student_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        self.current_student_id = self.student_ids[index]
        self.load_student_data()

    def load_student_data(self):
        if self.current_student_id is None:
            return
        info = self.db.get_student_info(self.current_student_id)
        if info:
            self.student_info_label.config(text=f"{info[0]}   |   Группа: {info[1]}")

        for row in self.tree.get_children():
            self.tree.delete(row)

        scores = self.db.get_scores_for_student(self.current_student_id, self.current_semester)
        grade_sum = 0
        count = 0
        for disc_name, att, ass, cre, exam, total in scores:
            grade = self.calc_grade(total)
            self.tree.insert('', tk.END, values=(
                disc_name,
                self.format_score(att),
                self.format_score(ass),
                self.format_score(cre),
                self.format_score(exam),
                self.format_score(total),
                grade
            ), tags=(f'grade_{grade}',))
            grade_sum += grade
            count += 1

        if count > 0:
            avg_grade = grade_sum / count
            self.avg_label.config(text=f"Средняя оценка: {avg_grade:.2f}  (дисциплин: {count})")
        else:
            self.avg_label.config(text="Средняя оценка: ---")

    def calc_grade(self, total):
        if total >= 85:
            return 5
        elif total >= 70:
            return 4
        elif total >= 50:
            return 3
        else:
            return 2

    # ---------- Добавление / удаление студента ----------
    def add_student_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Добавить студента")
        dialog.geometry("300x150")
        dialog.configure(bg=self.bg_color)
        ttk.Label(dialog, text="ФИО:").pack(pady=2)
        fio_entry = ttk.Entry(dialog, width=30)
        fio_entry.pack(pady=2)
        ttk.Label(dialog, text="Группа:").pack(pady=2)
        group_entry = ttk.Entry(dialog, width=30)
        group_entry.pack(pady=2)
        def save():
            fio = fio_entry.get().strip()
            group = group_entry.get().strip()
            if fio and group:
                if self.db.add_student(fio, group):
                    self.refresh_student_list()
                    dialog.destroy()
        ttk.Button(dialog, text="Добавить", command=save).pack(pady=5)

    def delete_student(self):
        if self.current_student_id is None:
            messagebox.showwarning("Предупреждение", "Выберите студента из списка")
            return
        if messagebox.askyesno("Подтверждение", "Удалить выбранного студента и все его баллы?"):
            self.db.delete_student(self.current_student_id)
            self.current_student_id = None
            self.refresh_student_list()
            for row in self.tree.get_children():
                self.tree.delete(row)
            self.student_info_label.config(text="Выберите студента")
            self.avg_label.config(text="Средняя оценка: ---")

    # ---------- Управление дисциплинами ----------
    def open_discipline_manager(self):
        man = tk.Toplevel(self)
        man.title("Управление дисциплинами")
        man.geometry("400x350")
        man.configure(bg=self.bg_color)

        listbox = tk.Listbox(man, width=50, height=12, font=('Segoe UI', 10), bg='white',
                             selectbackground=self.accent_color, selectforeground='white')
        listbox.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        def refresh_disc_list():
            listbox.delete(0, tk.END)
            discs = self.db.get_all_disciplines()
            self.disc_ids = [d[0] for d in discs]
            for d in discs:
                listbox.insert(tk.END, f"{d[1]} (семестр {d[2]})")

        refresh_disc_list()

        frame_fields = ttk.Frame(man)
        frame_fields.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(frame_fields, text="Название:").grid(row=0, column=0, sticky=tk.W)
        name_entry = ttk.Entry(frame_fields, width=25)
        name_entry.grid(row=0, column=1, padx=5)
        ttk.Label(frame_fields, text="Семестр:").grid(row=1, column=0, sticky=tk.W, pady=5)
        sem_entry = ttk.Entry(frame_fields, width=5)
        sem_entry.grid(row=1, column=1, padx=5, sticky=tk.W)
        sem_entry.insert(0, "1")

        def add_disc():
            name = name_entry.get().strip()
            sem = sem_entry.get().strip()
            if not name or not sem.isdigit():
                messagebox.showwarning("Ошибка", "Введите название и номер семестра (цифру)")
                return
            if self.db.add_discipline(name, int(sem)):
                name_entry.delete(0, tk.END)
                sem_entry.delete(0, tk.END)
                sem_entry.insert(0, "1")
                refresh_disc_list()
                self.refresh_semester_selector()

        def delete_disc():
            sel = listbox.curselection()
            if sel:
                disc_name = listbox.get(sel[0]).split(" (семестр")[0]
                disc_id = self.disc_ids[sel[0]]
                if messagebox.askyesno("Подтверждение", f"Удалить дисциплину '{disc_name}'? Все баллы по ней будут потеряны."):
                    self.db.delete_discipline(disc_id)
                    refresh_disc_list()
                    self.refresh_semester_selector()
                    if self.current_student_id:
                        self.load_student_data()

        btn_frame = ttk.Frame(man)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Добавить", command=add_disc).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Удалить", command=delete_disc).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Закрыть", command=man.destroy).pack(side=tk.RIGHT, padx=2)

    # ---------- Баллы ----------
    def add_edit_scores(self):
        if self.current_student_id is None:
            messagebox.showwarning("Предупреждение", "Сначала выберите студента")
            return

        selected_row = self.tree.selection()
        if selected_row:
            disc_name = self.tree.item(selected_row[0], 'values')[0]
            self.db.cursor.execute('SELECT id FROM disciplines WHERE name=?', (disc_name,))
            disc_id = self.db.cursor.fetchone()[0]
            self.open_score_dialog(disc_id, disc_name)
        else:
            available = self.db.get_disciplines_not_for_student(self.current_student_id, self.current_semester)
            if not available:
                messagebox.showinfo("Информация", "У этого студента уже есть баллы по всем дисциплинам.")
                return
            choose = tk.Toplevel(self)
            choose.title("Выберите дисциплину")
            choose.geometry("300x150")
            choose.configure(bg=self.bg_color)
            ttk.Label(choose, text="Выберите дисциплину:").pack(pady=5)
            combo = ttk.Combobox(choose, values=[d[1] for d in available], state='readonly')
            combo.pack(pady=5)
            combo.current(0)

            def proceed():
                sel_disc_name = combo.get()
                disc_id = next((d[0] for d in available if d[1] == sel_disc_name), None)
                choose.destroy()
                self.open_score_dialog(disc_id, sel_disc_name)

            ttk.Button(choose, text="Далее", command=proceed).pack(pady=5)

    def open_score_dialog(self, disc_id, disc_name):
        self.db.cursor.execute('''SELECT attendance, assignments, creativity, exam 
                                 FROM scores WHERE student_id=? AND discipline_id=?''',
                               (self.current_student_id, disc_id))
        row = self.db.cursor.fetchone()
        cur_att, cur_ass, cur_cre, cur_exam = row if row else (0.0, 0.0, 0.0, 0.0)

        dialog = tk.Toplevel(self)
        dialog.title(f"Баллы: {disc_name}")
        dialog.geometry("300x300")
        dialog.configure(bg=self.bg_color)

        ttk.Label(dialog, text=f"Дисциплина: {disc_name}", font=('Segoe UI', 10, 'bold')).pack(pady=5)
        ttk.Label(dialog, text="Посещаемость (0–20):").pack()
        att_entry = ttk.Entry(dialog)
        att_entry.insert(0, self.format_score(cur_att))
        att_entry.pack(pady=2)
        ttk.Label(dialog, text="Текущий и рубежный контроль (0–20):").pack()
        ass_entry = ttk.Entry(dialog)
        ass_entry.insert(0, self.format_score(cur_ass))
        ass_entry.pack(pady=2)
        ttk.Label(dialog, text="Творческий рейтинг (0–20):").pack()
        cre_entry = ttk.Entry(dialog)
        cre_entry.insert(0, self.format_score(cur_cre))
        cre_entry.pack(pady=2)
        ttk.Label(dialog, text="Экзамен (0–40):").pack()
        exam_entry = ttk.Entry(dialog)
        exam_entry.insert(0, self.format_score(cur_exam))
        exam_entry.pack(pady=2)

        def save():
            try:
                att = float(att_entry.get())
                ass = float(ass_entry.get())
                cre = float(cre_entry.get())
                exam = float(exam_entry.get())
                if not (0 <= att <= 20 and 0 <= ass <= 20 and 0 <= cre <= 20 and 0 <= exam <= 40):
                    messagebox.showwarning("Ошибка", "Баллы должны быть в пределах: 0–20 / 0–20 / 0–20 / 0–40")
                    return
            except ValueError:
                messagebox.showwarning("Ошибка", "Введите числовые значения (можно дробные, через точку)")
                return
            self.db.save_scores(self.current_student_id, disc_id, att, ass, cre, exam)
            self.load_student_data()
            dialog.destroy()

        ttk.Button(dialog, text="Сохранить", command=save).pack(pady=10)

    # ---------- Удаление баллов ----------
    def delete_score(self):
        if self.current_student_id is None:
            messagebox.showwarning("Предупреждение", "Сначала выберите студента")
            return
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите дисциплину для удаления")
            return
        disc_name = self.tree.item(selected[0], 'values')[0]
        self.db.cursor.execute('SELECT id FROM disciplines WHERE name=?', (disc_name,))
        disc_id = self.db.cursor.fetchone()[0]
        if messagebox.askyesno("Подтверждение", f"Удалить баллы по дисциплине '{disc_name}'?"):
            self.db.delete_score(self.current_student_id, disc_id)
            self.load_student_data()

    # ---------- Экспорт ведомости ----------
    def export_student_csv(self):
        if self.current_student_id is None:
            messagebox.showwarning("Предупреждение", "Выберите студента для экспорта")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".csv",
                                                filetypes=[("CSV files", "*.csv")],
                                                title="Сохранить ведомость студента")
        if not filename:
            return
        info = self.db.get_student_info(self.current_student_id)
        scores = self.db.get_scores_for_student(self.current_student_id, self.current_semester)
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['Студент', info[0], 'Группа', info[1]])
            if self.current_semester:
                writer.writerow([f"Семестр {self.current_semester}"])
            writer.writerow([])
            writer.writerow(['Дисциплина', 'Посещаемость (20)', 'Текущий и рубежный контроль (20)',
                             'Творческий рейтинг (20)', 'Экзамен (40)', 'Итог', 'Оценка'])
            total_sum = 0
            grade_sum = 0
            count = 0
            for disc_name, att, ass, cre, exam, total in scores:
                grade = self.calc_grade(total)
                writer.writerow([disc_name,
                                 self.format_score(att),
                                 self.format_score(ass),
                                 self.format_score(cre),
                                 self.format_score(exam),
                                 self.format_score(total),
                                 grade])
                total_sum += total
                grade_sum += grade
                count += 1
            if count > 0:
                avg_total = total_sum / count
                avg_grade = grade_sum / count
                writer.writerow([])
                writer.writerow(['Среднее', '', '', '', '',
                                 self.format_score(avg_total),
                                 self.format_score(avg_grade)])
        messagebox.showinfo("Успех", f"Ведомость сохранена в {filename}")

    # ---------- График успеваемости студента ----------
    def show_student_graph(self):
        if self.current_student_id is None:
            messagebox.showwarning("Предупреждение", "Сначала выберите студента")
            return
        scores = self.db.get_scores_for_student(self.current_student_id, self.current_semester)
        if not scores:
            messagebox.showinfo("Информация", "Нет данных для графика")
            return

        disc_names = []
        att_vals = []
        ass_vals = []
        cre_vals = []
        exam_vals = []
        total_vals = []
        for name, att, ass, cre, exam, total in scores:
            disc_names.append(name)
            att_vals.append(att)
            ass_vals.append(ass)
            cre_vals.append(cre)
            exam_vals.append(exam)
            total_vals.append(total)

        # Создаём окно с графиком
        graph_win = tk.Toplevel(self)
        graph_win.title(f"Успеваемость: {self.db.get_student_info(self.current_student_id)[0]}")
        graph_win.geometry("700x500")
        graph_win.configure(bg='white')

        fig = Figure(figsize=(7, 4), dpi=100)
        ax = fig.add_subplot(111)

        x = range(len(disc_names))
        width = 0.2
        ax.bar([i - 1.5*width for i in x], att_vals, width, label='Посещаемость', color='#3498db')
        ax.bar([i - 0.5*width for i in x], ass_vals, width, label='Текущий и рубежный контроль', color='#2ecc71')
        ax.bar([i + 0.5*width for i in x], cre_vals, width, label='Творческий рейтинг', color='#f1c40f')
        ax.bar([i + 1.5*width for i in x], exam_vals, width, label='Экзамен', color='#e74c3c')

        # Линия итога
        ax.plot(x, total_vals, 'k--', marker='o', label='Итог', linewidth=2)

        ax.set_xticks(x)
        ax.set_xticklabels(disc_names, rotation=45, ha='right')
        ax.set_ylabel('Баллы')
        ax.set_title('Баллы по дисциплинам')
        ax.legend()
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=graph_win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # ---------- Рейтинг студентов (с историей) ----------
    def show_rating(self):
        rating_window = tk.Toplevel(self)
        rating_window.title("Рейтинг студентов")
        rating_window.geometry("700x480")
        rating_window.configure(bg=self.bg_color)

        header = tk.Label(rating_window, text="РЕЙТИНГ СТУДЕНТОВ", font=('Segoe UI', 12, 'bold'),
                          bg=self.header_color, fg='white', pady=8)
        header.pack(fill=tk.X)

        sem_frame = ttk.Frame(rating_window)
        sem_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(sem_frame, text="Семестр:").pack(side=tk.LEFT)
        sem_combo = ttk.Combobox(sem_frame, state='readonly', width=20)
        semesters = self.db.get_semesters()
        values = ["Все семестры"] + [f"{s} семестр" for s in semesters]
        sem_combo['values'] = values
        if self.current_semester is None:
            sem_combo.current(0)
        else:
            try:
                idx = values.index(f"{self.current_semester} семестр")
                sem_combo.current(idx)
            except ValueError:
                sem_combo.current(0)
        sem_combo.pack(side=tk.LEFT, padx=5)

        tree_frame = ttk.Frame(rating_window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        columns = ('rank', 'fio', 'group', 'avg', 'change_rank', 'change_avg')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=12)
        tree.heading('rank', text='Место')
        tree.heading('fio', text='ФИО')
        tree.heading('group', text='Группа')
        tree.heading('avg', text='Средний балл')
        tree.heading('change_rank', text='Δ Позиция')
        tree.heading('change_avg', text='Δ Балл')

        tree.column('rank', width=50, anchor=tk.CENTER)
        tree.column('fio', width=160, anchor=tk.W)
        tree.column('group', width=80, anchor=tk.CENTER)
        tree.column('avg', width=100, anchor=tk.CENTER)
        tree.column('change_rank', width=90, anchor=tk.CENTER)
        tree.column('change_avg', width=90, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def fill_rating(semester):
            tree.delete(*tree.get_children())
            if semester is None:
                data = self.db.get_all_students_with_avg_grade(semester=None)
                rank = 1
                prev_avg = None
                for i, (fio, group, avg) in enumerate(data):
                    if i == 0:
                        cur_rank = 1
                        prev_avg = avg
                    else:
                        if avg == prev_avg:
                            cur_rank = rank
                        else:
                            rank = i + 1
                            cur_rank = rank
                            prev_avg = avg
                    tree.insert('', tk.END, values=(
                        cur_rank, fio, group, self.format_score(avg), '—', '—'))
                return

            current_ranking = self.db.get_students_ranking(semester)
            prev_semester = semester - 1 if semester > 1 else None
            if prev_semester and self.db.get_semesters().count(prev_semester) > 0:
                prev_ranking = self.db.get_students_ranking(prev_semester)
                prev_dict = {sid: (avg, rank) for sid, _, _, avg, rank in prev_ranking}
            else:
                prev_dict = None

            for sid, fio, group, avg, cur_rank in current_ranking:
                avg_str = self.format_score(avg)
                if prev_dict and sid in prev_dict:
                    prev_avg, prev_rank = prev_dict[sid]
                    delta_rank = prev_rank - cur_rank
                    delta_avg_val = avg - prev_avg
                    if delta_rank > 0:
                        change_rank_str = f"↑{delta_rank}"
                    elif delta_rank < 0:
                        change_rank_str = f"↓{abs(delta_rank)}"
                    else:
                        change_rank_str = "–"
                    change_avg_str = f"{'+' if delta_avg_val > 0 else ''}{self.format_score(delta_avg_val)}"
                else:
                    change_rank_str = "New" if prev_dict is not None else '—'
                    change_avg_str = '—' if prev_dict is not None else '—'
                tree.insert('', tk.END, values=(
                    cur_rank, fio, group, avg_str, change_rank_str, change_avg_str))

        def on_sem_change(event):
            sel = sem_combo.get()
            if sel == "Все семестры":
                fill_rating(None)
            else:
                num = int(sel.split()[0])
                fill_rating(num)

        def show_group_graph():
            """График средних баллов всей группы/семестра"""
            # Получаем данные из текущего рейтинга
            data = []
            if sem_combo.get() == "Все семестры":
                raw = self.db.get_all_students_with_avg_grade(None)
                data = [(fio, avg) for fio, _, avg in raw]
            else:
                num = int(sem_combo.get().split()[0])
                ranking = self.db.get_students_ranking(num)
                data = [(fio, avg) for _, fio, _, avg, _ in ranking]

            if not data:
                messagebox.showinfo("Нет данных", "Нет данных для графика")
                return

            names = [item[0] for item in data]
            avgs = [item[1] for item in data]

            fig2 = Figure(figsize=(6, 4), dpi=100)
            ax2 = fig2.add_subplot(111)
            bars = ax2.bar(names, avgs, color='#2e86c1')
            ax2.set_ylabel('Средний балл')
            ax2.set_title('Рейтинг студентов')
            ax2.set_xticklabels(names, rotation=45, ha='right')
            ax2.grid(axis='y', linestyle='--', alpha=0.7)
            fig2.tight_layout()

            graph_win2 = tk.Toplevel(rating_window)
            graph_win2.title("График рейтинга")
            graph_win2.geometry("600x400")
            graph_win2.configure(bg='white')
            canvas2 = FigureCanvasTkAgg(fig2, master=graph_win2)
            canvas2.draw()
            canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(rating_window)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="📊 График", command=show_group_graph).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Закрыть", command=rating_window.destroy).pack(side=tk.RIGHT)

        sem_combo.bind('<<ComboboxSelected>>', on_sem_change)
        fill_rating(self.current_semester)

    def on_closing(self):
        self.db.close()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()