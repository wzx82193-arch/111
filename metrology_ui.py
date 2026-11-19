"""Interactive raceway selection and dimensional results."""
import csv
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
import numpy as np

from core import acquisition_sections, load
from metrology import fit_arc, fit_groove, pitch_diameter

SLOTS = ('A 左弧', 'A 右弧', 'B 左弧', 'B 右弧', 'C 左弧', 'C 右弧')
COLORS = ('#00729d', '#c04c2b', '#5f4b8b')


def scan_sections(dataset, xi, yi):
    x, y = dataset.values[:, xi], dataset.values[:, yi]
    valid = ~(dataset.invalid[:, xi] | dataset.invalid[:, yi])
    cuts = acquisition_sections(x)
    return [(x[lo:hi][valid[lo:hi]], y[lo:hi][valid[lo:hi]])
            for lo, hi in zip(cuts[:-1], cuts[1:])]


class MetrologyWindow:
    def __init__(self, parent, path, dataset, xi, yi):
        self.window = tk.Toplevel(parent)
        self.window.title('滚珠丝杠与螺母滚道参数')
        self.window.geometry('1260x790')
        self.window.minsize(1030, 680)
        self.window.columnconfigure(1, weight=1)
        self.window.rowconfigure(0, weight=1)
        self.original = scan_sections(dataset, xi, yi)
        self.traces = [self.original, self.original]
        self.sources = [path.resolve(), path.resolve()]
        self.frame = ttk.Frame(self.window, padding=12)
        self.frame.grid(row=0, column=0, sticky='ns')
        self.frame.columnconfigure(1, weight=1)
        self.part = self.choice(0, '零件类型', ('丝杠', '螺母'))
        self.opening = self.choice(1, 'A 槽开口方向', ('+Y', '−Y'))
        self.ball = self.field(2, '实测或指定球径 (mm)')
        self.x_scale = self.field(3, 'X 系数 (mm/原单位)', '1')
        self.y_scale = self.field(4, 'Y 系数 (mm/原单位)', '1')
        self.axis = self.field(5, '已标定轴线 Y (mm)，可空')
        self.offset = self.field(6, 'B → A 的 Y 标定偏置 (mm)', '0')
        self.starts = self.field(7, '螺纹头数，可空')
        self.calibrated = tk.BooleanVar(self.window)
        ttk.Checkbutton(self.frame, text='已核实单位、对径位置及共同径向基准',
                        variable=self.calibrated).grid(row=8, columnspan=2, sticky='w', pady=(4, 3))
        self.scans = [self.choice(9, 'A / C 所用扫描段', ()),
                      self.choice(10, 'B 所用扫描段', ())]
        ttk.Button(self.frame, text='另载 B 侧文件', command=self.load_b).grid(
            row=11, columnspan=2, sticky='ew', pady=3)
        self.slot = self.choice(12, '拖选写入的区间', SLOTS)
        self.slot.bind('<<ComboboxSelected>>', self.highlight_slot)
        ttk.Label(self.frame, text='A 主槽 · B 对径槽（可选） · C 同侧相邻槽（可选）',
                  wraplength=335).grid(row=13, columnspan=2, sticky='w', pady=(4, 0))
        self.ranges = []
        for index, label in enumerate(SLOTS):
            field = self.field(14+index, f'{label}  起点, 终点')
            self.ranges.append(field)
        ttk.Button(self.frame, text='计算滚道参数', style='Accent.TButton',
                   command=self.calculate).grid(row=20, columnspan=2, sticky='ew', pady=(8, 3))
        ttk.Button(self.frame, text='导出结果 CSV', command=self.export).grid(
            row=21, columnspan=2, sticky='ew', pady=3)

        display = ttk.Frame(self.window, padding=(0, 8, 10, 8))
        display.grid(row=0, column=1, sticky='nsew')
        pane = ttk.Panedwindow(display, orient='vertical')
        pane.pack(fill='both', expand=True)
        chart = ttk.Frame(pane)
        result = ttk.Frame(pane)
        pane.add(chart, weight=3)
        pane.add(result, weight=2)
        self.figure = Figure(layout='constrained')
        self.axes = self.figure.subplots(2, 1)
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.toolbar = NavigationToolbar2Tk(self.canvas, chart)
        self.toolbar.update()
        self.selectors = []
        self.overlays = []
        self.result = tk.Text(result, height=10, wrap='word', relief='flat', padx=8, pady=6)
        scroll = ttk.Scrollbar(result, command=self.result.yview)
        self.result.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.result.pack(fill='both', expand=True)
        self.rows = []
        self.record = []
        for index, control in enumerate(self.scans):
            self.set_scans(index)
            control.current(min(index, len(self.traces[index])-1))
            control.bind('<<ComboboxSelected>>', lambda event, i=index: self.changed_scan(i))
        self.draw_traces()
        self.set_result('先用工具栏放大单个沟槽，退出缩放模式后在对应图中横向拖选。'
                        '每个槽选两个弧段，避开槽底过渡和台面。也可直接输入起点和终点。')

    def field(self, row, label, initial=''):
        ttk.Label(self.frame, text=label).grid(row=row, column=0, sticky='w', padx=(0, 5), pady=2)
        control = ttk.Entry(self.frame, width=16)
        control.insert(0, initial)
        control.grid(row=row, column=1, sticky='ew', pady=2)
        return control

    def choice(self, row, label, values):
        ttk.Label(self.frame, text=label).grid(row=row, column=0, sticky='w', padx=(0, 5), pady=2)
        control = ttk.Combobox(self.frame, width=14, state='readonly', values=values)
        control.grid(row=row, column=1, sticky='ew', pady=2)
        if values:
            control.current(0)
        return control

    def set_scans(self, index):
        control = self.scans[index]
        control.configure(values=[f'扫描段 {i+1}' for i in range(len(self.traces[index]))])
        control.current(0)

    def scan(self, index):
        return self.traces[index][self.scans[index].current()]

    def changed_scan(self, index):
        for slot in ((0, 1, 4, 5) if index == 0 else (2, 3)):
            self.ranges[slot].delete(0, 'end')
        self.draw_traces()
        self.rows = []
        self.calibrated.set(False)
        self.set_result('扫描段已更新，请重新选择该侧区间。')

    def load_b(self):
        path = filedialog.askopenfilename(parent=self.window, filetypes=[
            ('测量数据', '*.txt *.csv *.tsv'), ('所有文件', '*.*')])
        if path:
            try:
                d = load(path)
                self.traces[1] = scan_sections(d, d.default_x, d.default_y)
            except (OSError, ValueError) as error:
                messagebox.showerror('读取 B 侧失败', str(error), parent=self.window)
                return
            self.sources[1] = Path(path).resolve()
            self.set_scans(1)
            self.changed_scan(1)

    def draw_traces(self):
        for selector in self.selectors:
            selector.disconnect_events()
        self.selectors.clear()
        self.overlays.clear()
        for i, ax in enumerate(self.axes):
            x, y = self.scan(i)
            ax.clear()
            ax.plot(x, y, lw=.65, color='#455c66')
            ax.set_title(f'{"A / C" if i==0 else "B"}  ·  {self.sources[i].name}', loc='left', fontsize=10)
            ax.set_ylabel('原始 Y')
            ax.grid(alpha=.18)
            selector = SpanSelector(ax, lambda low, high, index=i: self.selected(index, low, high),
                                    'horizontal', useblit=True,
                                    props={'facecolor': '#208e79', 'alpha': .25})
            self.selectors.append(selector)
        self.axes[-1].set_xlabel('原始 X')
        self.toolbar.update()
        self.highlight_slot()
        self.canvas.draw_idle()

    def highlight_slot(self, event=None):
        selected_axis = int(self.slot.current() in (2, 3))
        for index, selector in enumerate(self.selectors):
            selector.set_active(index == selected_axis)

    def selected(self, index, lower, upper):
        slot = self.slot.current()
        if lower >= upper or index != int(slot in (2, 3)):
            return
        field = self.ranges[slot]
        field.delete(0, 'end')
        field.insert(0, f'{lower:.9g}, {upper:.9g}')

    @staticmethod
    def number(field, label, optional=False, positive=False):
        text = field.get().strip()
        if optional and not text:
            return None
        try:
            number = float(text)
        except ValueError:
            raise ValueError(f'请输入有效的{label}。') from None
        if not np.isfinite(number) or (positive and number <= 0):
            raise ValueError(f'请检查{label}的数值。')
        return number

    def arc_points(self, slot, x, y):
        label = SLOTS[slot]
        text = self.ranges[slot].get().strip().replace('，', ',')
        if not text:
            raise ValueError(f'尚未填写 {label} 区间。')
        try:
            low, high = (float(value) for value in text.split(','))
        except ValueError:
            raise ValueError(f'{label} 格式应为「起点, 终点」。') from None
        if not np.isfinite([low, high]).all() or low >= high:
            raise ValueError(f'{label} 区间的起点应小于终点。')
        selected = (x >= low) & (x <= high)
        order = np.argsort(x[selected], kind='stable')
        return x[selected][order], y[selected][order], low, high

    def set_result(self, value):
        self.result.configure(state='normal')
        self.result.delete('1.0', 'end')
        self.result.insert('end', value)
        self.result.configure(state='disabled')

    def calculate(self):
        self.rows = []
        for item in self.overlays:
            item.remove()
        self.overlays.clear()
        try:
            rows, warnings = self.compute()
        except (ValueError, np.linalg.LinAlgError) as error:
            self.set_result(str(error))
        else:
            self.rows = rows
            fields = (self.ball, self.x_scale, self.y_scale, self.axis, self.offset, self.starts)
            self.record = [self.part.get(), self.opening.get(), self.calibrated.get(),
                           self.sources[0].name, self.scans[0].get(),
                           self.sources[1].name, self.scans[1].get(),
                           *(field.get() for field in (*fields, *self.ranges))]
            lines = [f'{group}  {label}    {value:.9g} {unit}' for group, label, value, unit in rows]
            self.set_result('\n'.join([*warnings, *lines]))
        self.canvas.draw_idle()

    def compute(self):
        sx = self.number(self.x_scale, 'X 换算系数', positive=True)
        sy = self.number(self.y_scale, 'Y 换算系数', positive=True)
        axis_y = self.number(self.axis, '轴线 Y', optional=True)
        b_offset = self.number(self.offset, 'B 侧 Y 偏置')
        ball = self.number(self.ball, '球径', optional=True, positive=True)
        starts = self.number(self.starts, '螺纹头数', optional=True, positive=True)
        if starts is not None and not starts.is_integer():
            raise ValueError('螺纹头数必须为正整数。')
        opening = 1 if self.opening.current() == 0 else -1
        rows, warnings, grooves = [], [], {}
        if not any(field.get().strip() for field in self.ranges):
            raise ValueError('请先选择 A 槽的左右圆弧区间。')
        for group, name in enumerate('ABC'):
            pair = (2*group, 2*group+1)
            if not any(self.ranges[slot].get().strip() for slot in pair):
                continue
            side = int(name == 'B')
            offset = b_offset if side else 0
            x, y = self.scan(side)
            arcs, intervals = [], []
            for i, slot in enumerate(pair):
                try:
                    xx, yy, low, high = self.arc_points(slot, x, y)
                    arc = fit_arc(xx*sx, yy*sy+offset)
                except (ValueError, np.linalg.LinAlgError) as error:
                    warnings.append(f'{SLOTS[slot]}：{error}')
                    continue
                arcs.append(arc)
                intervals.append((low, high))
                half = '左' if i == 0 else '右'
                angle = np.linspace(arc.angles.min(), arc.angles.max(), 120)
                self.overlay(side, (arc.center[0]+arc.radius*np.cos(angle))/sx,
                             (arc.center[1]+arc.radius*np.sin(angle)-offset)/sy, group, lw=1.6)
                rows.extend((name, f'{half}弧{label}', value, unit) for label, value, unit in (
                    ('半径', arc.radius, 'mm'), ('圆心 X', arc.center[0], 'mm'),
                    ('圆心 Y', arc.center[1], 'mm'),
                    ('径向残差 RMSE', np.sqrt(np.mean(arc.residual**2)), 'mm'),
                    ('径向残差峰谷差', np.ptp(arc.residual), 'mm')))
                if ball is not None:
                    rows.append((name, f'{half}弧适合度（R / 球径）', arc.radius/ball, ''))
            if len(arcs) < 2:
                continue
            if intervals[0][1] > intervals[1][0]:
                warnings.append(f'{name} 槽的左右弧区间应依 X 从小到大且不能重叠。')
                continue
            rows.append((name, '左右弧圆心距', np.linalg.norm(arcs[0].center-arcs[1].center), 'mm'))
            if ball is None:
                continue
            if name == 'C' and self.same_groove():
                warnings.append('A、C 的选区重叠，请选择同侧相邻的两个不同槽。')
                continue
            try:
                groove = fit_groove(tuple(arcs), ball, -opening if side else opening)
            except ValueError as error:
                warnings.append(f'{name} 槽：{error}')
                continue
            grooves[name] = groove
            rows.extend((name, label, value, unit) for label, value, unit in (
                ('球心 X', groove.ball[0], 'mm'), ('球心 Y', groove.ball[1], 'mm'),
                ('左轴截面接触角', groove.contact_angles[0], '°'),
                ('右轴截面接触角', groove.contact_angles[1], '°')))
            theta = np.linspace(0, 2*np.pi, 160)
            self.overlay(side, (groove.ball[0]+ball/2*np.cos(theta))/sx,
                         (groove.ball[1]+ball/2*np.sin(theta)-offset)/sy, group, lw=1, ls='--')
            contacts = np.array(groove.contacts)
            self.overlay(side, contacts[:, 0]/sx, (contacts[:, 1]-offset)/sy, group,
                         marker='o', ls='none', ms=4)
        if ball is None:
            warnings.append('填写球径后可求双弧切点、球心和接触角。')
        pcd = self.add_diameter(rows, warnings, grooves, axis_y, opening)
        if 'A' in grooves and 'C' in grooves:
            pitch = abs(grooves['A'].ball[0]-grooves['C'].ball[0])
            rows.append(('A–C', '相邻滚道中心距（轴向螺距）', pitch, 'mm'))
            if starts is not None:
                lead = pitch*starts
                rows.append(('A–C', '估算导程', lead, 'mm'))
                if pcd:
                    rows.append(('A–C', '估算螺旋升角', np.degrees(np.arctan2(lead, np.pi*pcd)), '°'))
        return rows, warnings

    def same_groove(self):
        x, y = self.scan(0)
        try:
            boundaries = [self.arc_points(slot, x, y)[2:] for slot in (0, 1, 4, 5)]
        except ValueError:
            return False
        return max(boundaries[0][0], boundaries[2][0]) < min(boundaries[1][1], boundaries[3][1])

    def add_diameter(self, rows, warnings, grooves, axis_y, opening):
        if 'A' not in grooves:
            return None
        if not self.calibrated.get():
            warnings.append('节圆直径需要确认坐标标定。双侧计算还要求对径扫描共享径向基准。')
            return None
        if 'B' not in grooves and any(field.get().strip() for field in self.ranges[2:4]):
            warnings.append('B 槽选区尚未得到球心，请修正选区后重新计算节圆直径。')
            return None
        if 'B' in grooves and self.sources[0] == self.sources[1] and self.scans[0].current() == self.scans[1].current():
            warnings.append('对径计算需要物理上不同侧的扫描，请给 B 选择另一段或导入 B 文件。')
            return None
        try:
            diameter = pitch_diameter(grooves['A'], grooves.get('B'), axis_y, opening, self.part.get())
        except ValueError as error:
            warnings.append(f'节圆直径：{error}')
            return None
        method = '双侧' if 'B' in grooves else '单侧轴线估算'
        rows.insert(0, (self.part.get(), f'节圆直径 PCD（{method}）', diameter, 'mm'))
        return diameter

    def overlay(self, side, x, y, group, **style):
        self.overlays.extend(self.axes[side].plot(x, y, color=COLORS[group], **style))

    def export(self):
        if not self.rows:
            messagebox.showinfo('导出参数', '请先获得计算结果。', parent=self.window)
            return
        path = filedialog.asksaveasfilename(parent=self.window, defaultextension='.csv',
                                            filetypes=[('CSV', '*.csv')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['分组', '参数', '数值', '单位', '零件', 'A 开口方向', '标定确认',
                                     'A/C 数据文件', 'A/C 扫描段', 'B 数据文件', 'B 扫描段',
                                     '球径 (mm)', 'X 换算系数', 'Y 换算系数', '轴线 Y (mm)',
                                     'B 的 Y 偏置 (mm)', '头数', *SLOTS])
                    writer.writerows([*row, *self.record] for row in self.rows)
            except OSError as error:
                messagebox.showerror('导出失败', str(error), parent=self.window)
