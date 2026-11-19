"""Import coordinate measurements and fit user-selected numeric columns."""
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
import csv
import numpy as np

MISSING_DISTANCE = -2147.483648
MODELS = ('原始曲线', '线性', '二次多项式', '三次多项式', '局部多项式平滑', '圆拟合')


@dataclass
class Dataset:
    columns: list
    values: np.ndarray
    invalid: np.ndarray
    default_x: int
    default_y: int


def load(path):
    for encoding in ('utf-8-sig', 'gb18030', 'utf-16'):
        try:
            content = Path(path).read_text(encoding=encoding)
            break
        except UnicodeError:
            continue
    else:
        raise ValueError('无法识别文件编码。')
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines:
        raise ValueError('文件没有数据。')
    sample = lines[0]
    delimiter = next((d for d in (',', '\t', ';') if d in sample), None)
    fields = next(csv.reader([sample], delimiter=delimiter)) if delimiter else sample.split()
    def numeric(field):
        try:
            float(field)
            return True
        except ValueError:
            return not field.strip()
    header = not all(map(numeric, fields))
    columns = [field.strip().strip('"') for field in fields] if header else [
        f'Column {i+1}' for i in range(len(fields))]
    if len(columns) < 2 or len(lines) <= header:
        raise ValueError('至少需要两列和一行数值数据。')
    body = lines[int(header):]
    if delimiter:
        def clean(field):
            if numeric(field):
                return field.strip() or 'nan'
            return 'nan'
        rows = csv.reader(body, delimiter=delimiter)
        values = np.array([[float(clean(field)) for field in row] for row in rows
                           if len(row) == len(columns)], dtype=float)
        if len(values) != len(body):
            raise ValueError('数据行的列数不一致，请检查分隔符。')
    else:
        values = np.genfromtxt(StringIO('\n'.join(body)), ndmin=2)
    if values.ndim != 2 or values.shape[1] != len(columns):
        raise ValueError('文件列数不一致。')
    invalid = ~np.isfinite(values)
    x, y = 0, 1
    if '编码器1' in columns and 'CH1-距离1' in columns:
        x, y = columns.index('编码器1'), columns.index('CH1-距离1')
        invalid[:, y] |= np.isclose(values[:, y], MISSING_DISTANCE, rtol=0, atol=1e-8)
        x_values = values[~invalid[:, x], x]
        if (not len(x_values) or np.ptp(x_values) == 0) and '时间戳' in columns:
            x = columns.index('时间戳')
    return Dataset(columns, values, invalid, x, y)


def acquisition_sections(x):
    delta = np.diff(x)
    steps = np.abs(delta[np.isfinite(delta) & (delta != 0)])
    if len(steps):
        cuts = np.flatnonzero(np.abs(delta) > 100 * np.median(steps)) + 1
        if len(cuts) <= 30:
            return np.r_[0, cuts, len(x)]
    return np.array([0, len(x)])


def runs(x, y, mask, cuts=()):
    indices = np.flatnonzero(mask)
    split = np.flatnonzero(np.diff(indices) != 1)+1
    if len(cuts):
        split = np.union1d(split, np.searchsorted(indices, cuts))
    return [(x[group], y[group]) for group in np.split(indices, split)
            if group.size]


def local_curve(x, y, window):
    """Local quadratic fits at sampled knots, independently per valid run."""
    if len(x) < 3:
        return y.copy()
    window = min(window, len(x))
    if np.allclose(np.diff(x), np.diff(x)[0], rtol=0.02, atol=1e-10) and x[0] != x[-1]:
        window -= (window + 1) % 2
        radius = window // 2
        offsets = np.arange(-radius, radius+1, dtype=float) / radius
        weights = np.linalg.pinv(np.column_stack((np.ones(window), offsets, offsets**2)))[0]
        result = np.convolve(y, weights, mode='same')
        for start in (0, len(y)-window):
            edge = slice(start, start+window)
            target = slice(0, radius) if start == 0 else slice(-radius, None)
            model = np.polynomial.Polynomial.fit(x[edge], y[edge], 2)
            result[target] = model(x[target])
        if len(y) == window:
            result = model(x)
        return result
    step = max(1, window // 6, len(x) // 12000)
    knots = np.unique(np.r_[np.arange(0, len(x), step), len(x)-1])
    predictions = []
    for index in knots:
        start = min(max(index-window//2, 0), len(x)-window)
        xx, yy = x[start:start+window], y[start:start+window]
        degree = min(2, np.unique(xx).size-1)
        predictions.append(np.polynomial.Polynomial.fit(xx, yy, degree)(x[index])
                           if degree else yy.mean())
    return np.interp(np.arange(len(x)), knots, predictions)


def fit(x, y, method, window):
    if method == MODELS[0]:
        return None
    if method == MODELS[4]:
        estimate = local_curve(x, y, window)
        return x, estimate, y-estimate, f'局部二次拟合 | 窗口 {window} 点'
    if method == MODELS[5]:
        if len(x) < 3:
            raise ValueError('圆拟合至少需要三个非共线点。')
        origin = np.array([x.mean(), y.mean()])
        xy = np.column_stack((x, y))-origin
        scale = np.max(np.abs(xy))
        if scale == 0:
            raise ValueError('所有坐标相同。')
        u, v = (xy/scale).T
        matrix = np.column_stack((2*u, 2*v, np.ones(len(u))))
        coeff, _, rank, _ = np.linalg.lstsq(matrix, u*u+v*v, rcond=None)
        if rank < 3:
            raise ValueError('圆拟合要求非共线点。')
        center = coeff[:2]*scale+origin
        radius = np.sqrt(coeff[2]+sum(coeff[:2]**2))*scale
        theta = np.arctan2(y-center[1], x-center[0])
        theta = np.unwrap(theta)
        angles = np.linspace(theta.min(), min(theta.max(), theta.min()+2*np.pi), 600)
        return (center[0]+radius*np.cos(angles), center[1]+radius*np.sin(angles),
                np.hypot(x-center[0], y-center[1])-radius,
                f'代数圆拟合 | R = {radius:.8g} | 圆心 ({center[0]:.8g}, {center[1]:.8g})')
    degree = MODELS.index(method)
    if len(x) <= degree or x.min() == x.max():
        raise ValueError('所选区间的有效横坐标不足。')
    model, diagnostics = np.polynomial.Polynomial.fit(x, y, degree, full=True)
    if diagnostics[1] < degree+1:
        raise ValueError('所选区间的不同横坐标不足。')
    grid = np.linspace(x.min(), x.max(), 700)
    coefficients = ', '.join(f'{coefficient:.7g}' for coefficient in model.coef)
    return grid, model(grid), y-model(x), (
        f'系数 c₀…cₙ = {coefficients} | 自变量缩放区间 [{x.min():.8g}, {x.max():.8g}] → [−1, 1]')
