"""Interactive Windows measurement and curve-fitting application."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib as mpl
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import numpy as np

from core import MODELS, acquisition_sections, fit, load, runs
from metrology_ui import MetrologyWindow

mpl.rcParams.update({'font.family': ['Microsoft YaHei', 'DejaVu Sans'], 'pdf.fonttype': 42})


class Studio:
    def __init__(self, root):
        self.root = root
        root.title('测量曲线分析')
        root.geometry('1180x760')
        root.minsize(900, 620)
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Accent.TButton', background='#17665c', foreground='white', padding=7)
        style.map('Accent.TButton', background=[('active', '#217c70')])
        self.paths = []
        self.dataset = None
        self.valid_plot = False

        top = tk.Frame(root, background='#142b38', padx=18, pady=12)
        top.pack(fill='x')
        tk.Label(top, text='测量曲线分析', background='#142b38', foreground='white',
                 font=('Microsoft YaHei UI', 17, 'bold')).pack(side='left')
        ttk.Button(top, text='导出图像', command=self.export).pack(side='right')
        ttk.Button(top, text='滚道参数', style='Accent.TButton', command=self.metrology).pack(
            side='right', padx=8)
        ttk.Button(top, text='导入文件夹', command=self.folder).pack(side='right', padx=8)
        ttk.Button(top, text='导入文件', command=self.files).pack(side='right')

        pane = ttk.Panedwindow(root, orient='horizontal')
        pane.pack(fill='both', expand=True, padx=12, pady=12)
        sidebar = ttk.Frame(pane, padding=9)
        chart = ttk.Frame(pane, padding=(10, 0))
        pane.add(sidebar, weight=0)
        pane.add(chart, weight=1)
        ttk.Label(sidebar, text='数据文件').pack(anchor='w')
        listing = ttk.Frame(sidebar)
        listing.pack(fill='both', expand=True, pady=(4, 10))
        self.listbox = tk.Listbox(listing, width=31, height=7, exportselection=False,
                                  selectbackground='#17665c', relief='flat')
        self.listbox.grid(row=0, column=0, sticky='nsew')
        listing.rowconfigure(0, weight=1)
        listing.columnconfigure(0, weight=1)
        for orientation, command, key, position in (
            ('horizontal', self.listbox.xview, 'xscrollcommand', (1, 0, 'ew')),
            ('vertical', self.listbox.yview, 'yscrollcommand', (0, 1, 'ns')),
        ):
            bar = ttk.Scrollbar(listing, orient=orientation, command=command)
            bar.grid(row=position[0], column=position[1], sticky=position[2])
            self.listbox.configure(**{key: bar.set})
        self.listbox.bind('<<ListboxSelect>>', self.select)
        self.x = self.combo(sidebar, '横轴', ())
        self.y = self.combo(sidebar, '纵轴', ())
        self.section = self.combo(sidebar, '扫描段', ('全部',))
        self.method = self.combo(sidebar, '拟合方法', MODELS)
        self.method.current(0)
        ttk.Label(sidebar, text='横轴范围（可留空）').pack(anchor='w', pady=(7, 2))
        limits = ttk.Frame(sidebar)
        limits.pack(fill='x')
        self.low = ttk.Entry(limits, width=11)
        self.high = ttk.Entry(limits, width=11)
        self.low.pack(side='left', fill='x', expand=True)
        self.high.pack(side='left', fill='x', expand=True, padx=(5, 0))
        ttk.Label(sidebar, text='局部拟合窗口（点）').pack(anchor='w', pady=(7, 2))
        self.window = ttk.Spinbox(sidebar, from_=3, to=2001, width=8)
        self.window.set('41')
        self.window.pack(anchor='w')
        ttk.Button(sidebar, text='更新曲线', style='Accent.TButton', command=self.render).pack(
            fill='x', pady=(12, 0))

        self.status = tk.StringVar(value='导入 TXT、CSV 或 TSV 数据开始分析。')
        ttk.Label(chart, textvariable=self.status, wraplength=560, justify='left',
                  padding=(4, 6)).pack(side='bottom', fill='x')
        self.figure = Figure(figsize=(7, 5), dpi=100, layout='constrained')
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        NavigationToolbar2Tk(self.canvas, chart).update()
        self.clear_chart()

    @staticmethod
    def combo(parent, label, options):
        ttk.Label(parent, text=label).pack(anchor='w', pady=(6, 2))
        control = ttk.Combobox(parent, values=options, state='readonly', width=24)
        control.pack(fill='x')
        return control

    def clear_chart(self):
        self.valid_plot = False
        self.figure.clear()
        ax = self.figure.subplots()
        ax.axis('off')
        ax.text(.5, .5, '请选择数据文件', ha='center', va='center',
                color='#435b62', transform=ax.transAxes)
        self.canvas.draw()

    def folder(self):
        directory = filedialog.askdirectory()
        if directory:
            base = Path(directory)
            self.populate(sorted(p for p in base.rglob('*') if p.suffix.lower() in
                                 ('.txt', '.csv', '.tsv') and p.is_file()), base)

    def files(self):
        names = filedialog.askopenfilenames(filetypes=[('数据文件', '*.csv *.txt *.tsv'),
                                                       ('所有文件', '*.*')])
        if names:
            self.populate([Path(name) for name in names])

    def populate(self, paths, base=None):
        if not paths:
            messagebox.showinfo('导入文件夹', '没有找到 TXT、CSV 或 TSV 文件。')
            return
        self.paths = paths
        self.listbox.delete(0, 'end')
        for path in paths:
            self.listbox.insert('end', str(path.relative_to(base)) if base else path.name)
        self.listbox.selection_set(0)
        self.select()

    def select(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        self.path = self.paths[selection[0]]
        self.dataset = None
        try:
            self.dataset = load(self.path)
        except (OSError, ValueError) as error:
            self.clear_chart()
            self.status.set(str(error))
            return
        labels = [f'{i+1}. {name}' for i, name in enumerate(self.dataset.columns)]
        for control, index in ((self.x, self.dataset.default_x), (self.y, self.dataset.default_y)):
            control.configure(values=labels)
            control.current(index)
        self.sections = acquisition_sections(self.dataset.values[:, self.dataset.default_x])
        self.section.configure(values=['全部', *[f'扫描段 {i}' for i in range(1, len(self.sections))]])
        self.section.current(0)
        self.low.delete(0, 'end')
        self.high.delete(0, 'end')
        self.method.current(0)
        self.render()

    def render(self):
        if self.dataset is None:
            return
        try:
            return self.draw_data()
        except (ValueError, np.linalg.LinAlgError) as error:
            self.clear_chart()
            self.status.set(str(error))
            messagebox.showwarning('曲线分析', str(error))

    def draw_data(self):
        d = self.dataset
        xi, yi = self.x.current(), self.y.current()
        x, y = d.values[:, xi], d.values[:, yi]
        finite = ~(d.invalid[:, xi] | d.invalid[:, yi])
        lower, upper = [float(field.get()) if field.get().strip() else default
                        for field, default in ((self.low, -np.inf), (self.high, np.inf))]
        if not lower <= upper:
            raise ValueError('横轴下限应小于或等于上限。')
        selected = finite & (x >= lower) & (x <= upper)
        section = self.section.current()
        if section:
            selected[:self.sections[section-1]] = False
            selected[self.sections[section]:] = False
        if not selected.any():
            raise ValueError('所选区间内没有有效点。')
        method = self.method.get()
        segments = runs(x, y, selected, self.sections[1:-1])
        window = 41
        if method == MODELS[4]:
            window = int(self.window.get())
            if not 3 <= window <= 2001:
                raise ValueError('平滑窗口须为 3 到 2001 之间的整数。')
        fits = ([fit(xx, yy, method, window) for xx, yy in segments] if method == MODELS[4]
                else [fit(x[selected], y[selected], method, window)])
        self.figure.clear()
        ax = self.figure.subplots()
        for index, (xx, yy) in enumerate(segments):
            ax.plot(xx, yy, color='#235e77', lw=0.85, marker='.' if len(xx)<3 else None,
                    label='测量点' if index == 0 else None)
        details = ''
        if fits[0] is not None:
            for index, (xp, yp, residuals, label) in enumerate(fits):
                ax.plot(xp, yp, color='#c45735', lw=1.3, label='拟合' if index == 0 else None)
            residual = np.concatenate([item[2] for item in fits])
            details = f'\n{fits[0][3]} | RMSE {np.sqrt(np.mean(residual ** 2)):.7g}'
            variance = np.sum((y[selected] - y[selected].mean())**2)
            if method != MODELS[5] and variance > 0:
                details += f' | R² {1-np.sum(residual**2)/variance:.5f}'
        if method == MODELS[5]:
            ax.set_aspect('equal', adjustable='datalim')
        ax.set(xlabel=d.columns[xi], ylabel=d.columns[yi], title=self.path.stem, xmargin=.02)
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(alpha=.18)
        ax.legend(loc='best', frameon=False)
        self.status.set(f'区间有效点 {selected.sum():,} / {len(x):,} | 全文件无效点 '
                        f'{(~finite).sum():,} | 均值 {y[selected].mean():.7g} | '
                        f'标准差 {y[selected].std():.7g} | 范围 '
                        f'[{y[selected].min():.7g}, {y[selected].max():.7g}]{details}')
        self.canvas.draw()
        self.valid_plot = True

    def export(self):
        if not self.valid_plot:
            messagebox.showinfo('导出图像', '请先绘制曲线。')
            return
        destination = filedialog.asksaveasfilename(defaultextension='.png',
            filetypes=[('PNG 600 dpi', '*.png'), ('PDF 矢量图', '*.pdf'), ('SVG 矢量图', '*.svg')])
        if destination:
            try:
                self.figure.savefig(destination, dpi=600, facecolor='white')
            except (OSError, ValueError) as error:
                messagebox.showerror('导出失败', str(error))

    def metrology(self):
        if self.dataset is None:
            messagebox.showinfo('滚道参数', '请先导入并选择滚道轮廓数据。')
            return
        if self.x.current() == self.y.current():
            messagebox.showinfo('滚道参数', '请分别选择轴向 X 列和径向 Y 列。')
            return
        return MetrologyWindow(self.root, self.path, self.dataset, self.x.current(), self.y.current())


if __name__ == '__main__':
    root = tk.Tk()
    studio = Studio(root)
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke':
        base = Path(sys.argv[2])
        studio.populate(sorted([*base.rglob('*.txt'), *base.rglob('*.csv')]), base)
        for index in range(len(studio.paths)):
            studio.listbox.selection_clear(0, 'end')
            studio.listbox.selection_set(index)
            studio.select()
            assert studio.valid_plot, studio.status.get()
        for method in range(1, len(MODELS)-1):
            studio.method.current(method)
            studio.draw_data()
        studio.figure.savefig(Path.cwd() / 'smoke.png')
        root.destroy()
    else:
        root.mainloop()
