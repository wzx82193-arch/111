"""Gothic-arch section geometry in calibrated axial/radial coordinates."""
from dataclasses import dataclass

import numpy as np


@dataclass
class Arc:
    center: np.ndarray
    radius: float
    residual: np.ndarray
    angles: np.ndarray


@dataclass
class Groove:
    arcs: tuple
    ball: np.ndarray
    contacts: tuple
    contact_angles: tuple


def fit_arc(x, y):
    if len(x) < 8 or len(np.unique(x)) < 8:
        raise ValueError('每段圆弧至少需要 8 个不同横坐标的测点。')
    points = np.column_stack((x, y))
    origin = points.mean(axis=0)
    scale = float(np.max(np.abs(points-origin)))
    uv = (points-origin)/scale
    design = np.column_stack((2*uv, np.ones(len(uv))))
    guess, _, rank, singular = np.linalg.lstsq(design, (uv**2).sum(axis=1), rcond=None)
    if rank < 3 or singular[-1] < 1e-5*singular[0]:
        raise ValueError('所选点接近直线，无法可靠拟合圆弧。')
    center = guess[:2]
    radius = np.sqrt(guess[2] + center @ center)
    for _ in range(45):
        delta = uv-center
        distances = np.maximum(np.linalg.norm(delta, axis=1), 1e-14)
        residual = distances-radius
        jacobian = np.column_stack((-delta/distances[:, None], -np.ones(len(uv))))
        step = np.linalg.lstsq(jacobian, -residual, rcond=None)[0]
        if np.linalg.norm(step) <= 1e-12 * max(1, radius):
            break
        cost = residual @ residual
        accepted = False
        for exponent in range(14):
            change = step * 0.5**exponent
            trial_center, trial_radius = center+change[:2], radius+change[2]
            trial = np.linalg.norm(uv-trial_center, axis=1)-trial_radius
            if trial_radius > 0 and trial @ trial < cost:
                center, radius = trial_center, trial_radius
                accepted = True
                break
        if not accepted:
            break
    delta = uv-center
    angles = np.unwrap(np.arctan2(delta[:, 1], delta[:, 0]))
    if not 8 <= np.degrees(np.ptp(angles)) <= 180:
        raise ValueError('圆弧角跨度须在 8° 至 180° 内，请重新选取单侧弧段。')
    return Arc(center*scale+origin, radius*scale,
               (np.linalg.norm(delta, axis=1)-radius)*scale, angles)


def fit_groove(arcs, ball_diameter, opening):
    left, right = arcs
    radii = np.array([left.radius, right.radius])-ball_diameter/2
    direction = right.center-left.center
    separation = np.linalg.norm(direction)
    if min(radii) <= 0:
        raise ValueError('滚珠半径须小于左右拟合圆弧半径。')
    if not abs(radii[0]-radii[1]) < separation < sum(radii):
        raise ValueError('以该球径无法与两段圆弧同时内切，请复核球径及选区。')
    unit = direction/separation
    along = (radii[0]**2-radii[1]**2+separation**2)/(2*separation)
    height = np.sqrt(max(0, radii[0]**2-along**2))
    middle = left.center+along*unit
    normal = np.array([-unit[1], unit[0]])
    candidates = []
    for ball in (middle+height*normal, middle-height*normal):
        contact_points, contact_angles = [], []
        for arc, radius in zip(arcs, radii):
            ray = (ball-arc.center)/radius
            angle = np.arctan2(ray[1], ray[0])
            midpoint = (arc.angles.min()+arc.angles.max())/2
            angle += 2*np.pi*round((midpoint-angle)/(2*np.pi))
            # Permit two degrees at a picked arc endpoint for cursor rounding.
            margin = np.radians(2)
            if opening*ray[1] >= 0 or not arc.angles.min()-margin <= angle <= arc.angles.max()+margin:
                break
            contact_points.append(arc.center+arc.radius*ray)
            contact_angles.append(float(np.degrees(np.arctan2(abs(ray[0]), abs(ray[1])))))
        if len(contact_points) == 2:
            candidates.append(Groove(arcs, ball, tuple(contact_points), tuple(contact_angles)))
    if len(candidates) != 1:
        raise ValueError('选区内没有唯一有效的双侧切点。请检查径向开口方向并扩大两侧圆弧选区。')
    return candidates[0]


def pitch_diameter(a, b, axis_y, opening, part):
    """Diameter between opposed ball centers in the same calibrated frame."""
    if b is None:
        if axis_y is None:
            raise ValueError('单侧估算需要输入已标定的轴线 Y。')
        expected = opening if part == '丝杠' else -opening
        if expected*(a.ball[1]-axis_y) <= 0:
            raise ValueError('轴线与 A 槽的零件类型或开口方向不一致。')
        return 2*abs(a.ball[1]-axis_y)
    expected = opening if part == '丝杠' else -opening
    if expected*(a.ball[1]-b.ball[1]) <= 0:
        raise ValueError('两侧球心的径向顺序与零件类型或开口方向不一致。')
    middle = (a.ball[1]+b.ball[1])/2 if axis_y is None else axis_y
    if (a.ball[1]-middle)*(b.ball[1]-middle) >= 0:
        raise ValueError('球心没有分居轴线两侧，请检查共坐标标定。')
    return abs(a.ball[1]-b.ball[1])
