"""Real-source maps and saved-run route comparisons; no solver or external calls."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path as MplPath
from matplotlib.ticker import MaxNLocator
from shapely import shortest_line
from shapely.geometry import Point, Polygon, LineString, box, shape
from shapely.ops import unary_union
from shapely.geometry.polygon import orient
from src.connectivity_view import diagnosis_data

P2 = {'paper': '#FCFAF7', 'ink': '#2D3238', 'muted': '#70757A', 'blue': '#D3EAF5',
      'apricot': '#F5D9B8', 'rose': '#E8C7D3', 'violet': '#D7D3EA',
      'blue_accent': '#5B9FBE', 'apricot_accent': '#D49757', 'rose_accent': '#B97589',
      'violet_accent': '#8177A8', 'rule': '#DDE3E7', 'panel': '#FFFDFC'}
OUT = ROOT / 'figures/visuals'
PDF_ONLY = False


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def theme():
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'font.size': 9,
        'axes.titlesize': 11, 'axes.labelsize': 8, 'xtick.labelsize': 7, 'ytick.labelsize': 7,
        'text.color': P2['ink'], 'axes.labelcolor': P2['muted'], 'axes.edgecolor': P2['rule'],
        'xtick.color': P2['muted'], 'ytick.color': P2['muted'], 'figure.facecolor': P2['paper'],
        'axes.facecolor': P2['panel'], 'savefig.facecolor': P2['paper'], 'svg.fonttype': 'none',
        'pdf.fonttype': 42, 'axes.unicode_minus': False, 'hatch.linewidth': .3})
    plt.rcParams['path.simplify'] = False


def polygon_patch(poly, **kwargs):
    poly = orient(poly, sign=1)
    vertices, codes = [], []
    for ring in [poly.exterior, *poly.interiors]:
        coords = list(ring.coords)
        vertices.extend(coords)
        codes.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(coords) - 2) + [MplPath.CLOSEPOLY])
    return PathPatch(MplPath(vertices, codes), **kwargs)


def draw_geometry(ax, geometry, *, face='none', edge=None, width=.6, alpha=1,
                  dash='solid', zorder=2, hatch=None):
    if geometry.is_empty:
        return
    edge = edge or P2['ink']
    if geometry.geom_type == 'Polygon':
        ax.add_patch(polygon_patch(geometry, facecolor=face, edgecolor=edge, linewidth=width,
                                  alpha=alpha, linestyle=dash, zorder=zorder, hatch=hatch))
    elif geometry.geom_type in {'LineString', 'LinearRing'}:
        xs, ys = geometry.xy
        ax.plot(xs, ys, color=edge, linewidth=width, alpha=alpha, linestyle=dash, zorder=zorder)
    elif geometry.geom_type == 'Point':
        ax.plot(geometry.x, geometry.y, 'o', color=edge, markersize=2.5, alpha=alpha, zorder=zorder)
    else:
        for part in getattr(geometry, 'geoms', []):
            draw_geometry(ax, part, face=face, edge=edge, width=width, alpha=alpha,
                          dash=dash, zorder=zorder, hatch=hatch)


def load_scene(scene_id):
    data = diagnosis_data(scene_id)
    data['plot_features'] = [(shape(f['geometry']), f['properties']) for f in data['features']
                             if f.get('geometry') is not None]
    return data


def trim_extent(bounds, ratio=None, padding=0):
    x0, y0, x1, y1 = bounds
    x0 -= padding; x1 += padding; y0 -= padding; y1 += padding
    if ratio is not None:
        width, height = x1 - x0, y1 - y0
        if width / height < ratio:
            extra = (height * ratio - width) / 2
            x0 -= extra; x1 += extra
        else:
            extra = (width / ratio - height) / 2
            y0 -= extra; y1 += extra
    return [x0, y0, x1, y1]


def scale(ax, bounds):
    x0, y0, x1, y1 = bounds
    width, height = x1 - x0, y1 - y0
    choices = [.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
    length = max(v for v in choices if v <= width * .24)
    x, y = x0 + width * .055, y0 + height * .065
    ax.plot([x, x + length], [y, y], color=P2['ink'], lw=2.2, zorder=30)
    for end in [x, x + length]:
        ax.plot([end, end], [y - height * .008, y + height * .008], color=P2['ink'], lw=.8, zorder=30)
    ax.text(x + length / 2, y + height * .018, f'{length:g} m', ha='center', va='bottom', fontsize=8,
            bbox={'facecolor': P2['paper'], 'edgecolor': 'none', 'pad': .5}, zorder=31)
    ax.annotate('网格北', xy=(.95, .93), xytext=(.95, .83), xycoords='axes fraction',
                ha='center', fontsize=7, arrowprops={'arrowstyle': '-|>', 'color': P2['muted'], 'lw': .8})


def draw_scene(ax, data, bounds, *, face_width=.8, context_alpha=1, rasterize_background=False):
    """One common source base, in meters, for every route mode."""
    window = box(*bounds)
    features = [(g, p) for g, p in data['plot_features'] if not g.is_empty and g.intersects(window)]
    lines = {'roads': [], 'native': [], 'rejected': [], 'other': []}
    background = {'BUILDING': [], 'GRASS': [], 'WATER': [], 'PARK': []}
    for g, p in features:
        if p['geometry_role'] != 'SOURCE_CONTEXT':
            continue
        kind = p.get('kind')
        if g.geom_type in {'Polygon', 'MultiPolygon'}:
            if kind in background:
                background[kind].extend([g] if g.geom_type == 'Polygon' else list(g.geoms))
        elif kind == 'BARRIER':
            draw_geometry(ax, g, edge=P2['ink'], width=.7, dash='dotted', alpha=context_alpha, zorder=7)
        elif g.geom_type == 'LineString':
            lines['other'].append(list(g.coords))
    for kind, face, edge, width, alpha, hatch, zorder in [
        ('BUILDING', P2['rule'], P2['muted'], .3, .82, None, 1),
        ('GRASS', P2['rose'], P2['rose_accent'], .25, 1., '...', 2),
        ('WATER', P2['violet'], P2['violet_accent'], .35, .8, None, 2),
        ('PARK', P2['apricot'], P2['apricot_accent'], .35, .3, None, 0)]:
        if kind == 'BUILDING':
            ax.add_collection(PatchCollection([polygon_patch(p) for p in background[kind]],
                facecolor=face, edgecolor=edge, linewidths=width, alpha=alpha * context_alpha, hatch=hatch, zorder=zorder))
        else:
            # Individual paths keep patterned background fills consistent in
            # Agg, SVG and PDF backends at clipped polygon boundaries.
            for polygon in background[kind]:
                draw_geometry(ax, polygon, face=face, edge=edge, width=width,
                              alpha=alpha * context_alpha, hatch=hatch, zorder=zorder)
    for g, p in features:
        role = p['geometry_role']
        if role == 'LEGAL_OMEGA':
            draw_geometry(ax, g, face=P2['blue'], edge=P2['blue_accent'], width=face_width * .45, alpha=.9, zorder=3)
        elif role == 'SOURCE_P':
            # Explicit ring lines avoid spurious dashed closing strokes from
            # compound unfilled Polygon paths in the PDF backend.
            draw_geometry(ax, g.boundary, edge=P2['blue_accent'] if p['old_population'] else P2['violet_accent'],
                          width=face_width, dash='solid' if p['old_population'] else (0, (3, 1.3)), zorder=5)
        elif role == 'INDEPENDENT_NATIVE_SOURCE_LINE':
            if p.get('status') == 'SOURCE_AREA_BOUNDARY_NOT_INDEPENDENT_NATIVE_LINE':
                continue
            category = 'roads' if p.get('kind') == 'ROAD' else 'native' if p.get('status') == 'ELIGIBLE_NATIVE_LINEAR_TAGS' else 'rejected'
            if g.geom_type == 'LineString':
                lines[category].append(list(g.coords))
        elif role == 'UNCHANGED_REGISTERED_DOOR':
            ax.plot(g.x, g.y, marker='s', color=P2['ink'], markerfacecolor=P2['paper'], markersize=4.5, zorder=14)
        elif role == 'SOURCE_TAGGED_NODE' and p.get('tags', {}).get('barrier'):
            ax.plot(g.x, g.y, marker='+', color=P2['ink'], markersize=4, markeredgewidth=.8, zorder=10)
    for name, color, width, alpha, dash, zorder in [
        ('other', P2['rule'], .35, .6, 'solid', 1),
        ('roads', P2['muted'], .65, .65, (0, (3, 2)), 4),
        ('rejected', P2['muted'], .55, .65, 'dotted', 6),
        ('native', P2['ink'], .8, .8, 'solid', 8)]:
        collection = LineCollection(lines[name], colors=color, linewidths=width,
                                    alpha=alpha * context_alpha, linestyles=dash, zorder=zorder)
        if name != 'native':
            collection.set_gid('raw_context_lines_' + name)
        ax.add_collection(collection)
    ax.set_xlim(bounds[0], bounds[2]); ax.set_ylim(bounds[1], bounds[3]); ax.set_aspect('equal')
    if rasterize_background:
        ax.set_rasterization_zorder(2.9)
    ax.ticklabel_format(axis='both', style='plain', useOffset=False)
    ax.xaxis.set_major_locator(MaxNLocator(4)); ax.yaxis.set_major_locator(MaxNLocator(4))
    ax.tick_params(length=2, width=.5)
    ax.set_xlabel('E / m · EPSG:32651'); ax.set_ylabel('N / m')
    scale(ax, bounds)
    return features


def label(ax, xy, text, offset=(8, 8), *, color=None, size=8):
    annotation = ax.annotate(text, xy=xy, xytext=offset, textcoords='offset points',
        fontsize=size, color=color or P2['ink'], ha='left', va='bottom', zorder=45,
        arrowprops={'arrowstyle': '-', 'color': P2['muted'], 'linewidth': .55},
        bbox={'facecolor': P2['paper'], 'edgecolor': 'none', 'alpha': .93, 'pad': 1.5})
    return annotation


def legend_handles(routes=False):
    handles = [Patch(facecolor=P2['blue'], edgecolor=P2['blue_accent'], label='合法计算面 Ω'),
        Line2D([], [], color=P2['blue_accent'], label='旧集合原始边界 P'),
        Line2D([], [], color=P2['violet_accent'], linestyle='--', label='旧数据遗漏的原始面 P'),
        Line2D([], [], color=P2['ink'], label='原生步行线'),
        Line2D([], [], color=P2['muted'], linestyle='--', label='机动车道中心线（非路宽）'),
        Patch(facecolor=P2['rule'], edgecolor=P2['muted'], label='源建筑'),
        Patch(facecolor=P2['rose'], hatch='...', edgecolor=P2['rose_accent'], label='源草地 / 花坛（非步行面）'),
        Line2D([], [], marker='s', markerfacecolor=P2['paper'], color=P2['ink'], linestyle='none', label='原登记门（未移动）'),
        Patch(facecolor=P2['apricot'], edgecolor=P2['apricot_accent'], alpha=.4, label='源公园（背景）'),
        Patch(facecolor=P2['violet'], edgecolor=P2['violet_accent'], label='源水体')]
    handles.append(Line2D([], [], marker='+', color=P2['ink'], linestyle='none', label='源障碍节点（barrier）'))
    if routes:
        handles.extend([Line2D([], [], color=P2['rose_accent'], linestyle='--', lw=2, label='对照模式路线'),
            Line2D([], [], color=P2['ink'], lw=2, label='比较模式路线'),
            Line2D([], [], color=P2['apricot_accent'], linestyle='--', lw=2.5, label='条件接缝（假设）'),
            Line2D([], [], color=P2['apricot_accent'], linestyle='dotted', lw=2.3, label='原门前假设段'),
            Line2D([], [], marker='o', color=P2['blue_accent'], linestyle='none', label='路线使用的真实源接口'),
            Line2D([], [], color=P2['rose_accent'], linestyle='dotted', lw=1, label='被拒接缝候选'),
            Patch(facecolor=P2['apricot'], hatch='//', edgecolor=P2['apricot_accent'], label='原门前假设域')])
    return handles


def save(fig, name, metadata):
    OUT.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix in (('pdf',) if PDF_ONLY else ('svg', 'pdf', 'png')):
        path = OUT / f'{name}.{suffix}'
        spatial = 'scene_id' in metadata
        all_axes = fig.findobj(match=Axes)
        previous_raster = [ax.get_rasterization_zorder() for ax in all_axes]
        context_lines = [(item, item.get_rasterized()) for ax in all_axes for item in ax.collections
                         if (item.get_gid() or '').startswith('raw_context_lines_')]
        source_boundaries = [(item, item.get_rasterized()) for ax in all_axes for item in ax.lines
                             if item.get_zorder() == 5]
        if suffix == 'pdf' and spatial:
            for ax in all_axes:
                ax.set_rasterization_zorder(2.9)
            for item, _ in context_lines:
                item.set_rasterized(True)
            for item, _ in source_boundaries:
                item.set_rasterized(True)
        fig.savefig(path, dpi=300, bbox_inches='tight', pad_inches=.08,
                    **({'pil_kwargs': {'optimize': True}} if suffix == 'png' else {}))
        for ax, previous in zip(all_axes, previous_raster):
            ax.set_rasterization_zorder(previous)
        for item, previous in context_lines:
            item.set_rasterized(previous)
        for item, previous in source_boundaries:
            item.set_rasterized(previous)
        paths.append({'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
                      'sha256': sha256(path.read_bytes()).hexdigest()})
    if PDF_ONLY:
        paths = [{'path': (OUT / f'{name}.{suffix}').relative_to(ROOT).as_posix(),
                  'bytes': (OUT / f'{name}.{suffix}').stat().st_size,
                  'sha256': sha256((OUT / f'{name}.{suffix}').read_bytes()).hexdigest()}
                 for suffix in ('svg', 'pdf', 'png')]
    metadata.update(outputs=paths, crs='EPSG:32651', routes_recomputed=False, external_map_requests=0,
        source='© OpenStreetMap contributors · ODbL · frozen 2026-11-08T21:21:00Z',
        palette='P2 Cloud Sorbet Exact', renderer='Matplotlib', author_visual_review='PENDING_RENDER_INSPECTION')
    if 'scene_id' in metadata:
        metadata['pdf_background_export'] = 'SOURCE_CONTEXT_NON_ADMITTED_LINES_AND_P_OUTLINE_DASHES_RASTERIZED_AT_300DPI_TO_AVOID_BACKEND_CLIPPING_ARTIFACTS; OMEGA_ADMITTED_NATIVE_LINES_ROUTES_TEXT_REMAIN_VECTOR; SVG_FULLY_VECTOR'
    (OUT / f'{name}.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    plt.close(fig)
    return paths


def museum_source():
    data = load_scene('sh-huangpu-01')
    faces = {p['source_id']: g for g, p in data['plot_features'] if p['geometry_role'] == 'SOURCE_P'}
    north, south = faces['relation/2153738'], faces['relation/2385771']
    northeast = next(g for g, p in data['plot_features'] if p.get('source_id') == 'way/564255372' and p['geometry_role'] == 'INDEPENDENT_NATIVE_SOURCE_LINE')
    face_gap = shortest_line(south, north); line_gap = shortest_line(south, northeast)
    fig = plt.figure(figsize=(13.2, 7.5))
    grid = fig.add_gridspec(2, 2, width_ratios=[1.45, 1], left=.065, right=.975, bottom=.20, top=.88, wspace=.21, hspace=.35)
    main = fig.add_subplot(grid[:, 0]); upper = fig.add_subplot(grid[0, 1]); lower = fig.add_subplot(grid[1, 1])
    overview = trim_extent([354060, 3455980, 354560, 3456460], ratio=1.08)
    draw_scene(main, data, overview)
    main.set_title('a  街区总览：两旧面、建筑与独立步道', loc='left', pad=8)
    label(main, north.representative_point().coords[0], '人民广场 · relation/2153738', (-48, 32), size=8)
    label(main, south.representative_point().coords[0], '南门前面 · relation/2385771', (-124, -38), size=8)
    building = next(g for g, p in data['plot_features'] if p.get('id') == 'way/161090899' and p['geometry_role'] == 'SOURCE_CONTEXT')
    label(main, building.centroid.coords[0], '上海博物馆\nway/161090899', (-8, -14), size=8)
    for ax, connector, title, bounds, detail in [
        (upper, face_gap, 'b  面间原始间隙：10.30 m', [354418, 3456115, 354494, 3456178], 'P 最近距离 10.30 m；Ω 10.66 m\n超过本轮 5 m 接缝上限'),
        (lower, line_gap, 'c  源线链存在：直接间隙 7.07 m', [354449, 3456093, 354514, 3456145], '长步道 way/564255372；中间线 way/178737608\n源中共享节点线链存在；当前图续行另验\n原始源线不等同当前已放行线')]:
        bounds = trim_extent(bounds, ratio=1.75)
        draw_scene(ax, data, bounds, face_width=1.0)
        draw_geometry(ax, connector, edge=P2['ink'], width=1.1, dash='dotted', zorder=25)
        for xy in connector.coords:
            ax.plot(*xy, marker='o', markerfacecolor=P2['paper'], markeredgecolor=P2['ink'], markersize=3, zorder=26)
        ax.set_title(title, loc='left', pad=7)
        ax.text(.02, .98, detail, transform=ax.transAxes, va='top', fontsize=8,
                bbox={'facecolor': P2['paper'], 'edgecolor': 'none', 'alpha': .95, 'pad': 2}, zorder=40)
        draw_geometry(main, box(*bounds), edge=P2['muted'], width=.7, dash='dotted', zorder=20)
    native_link = next(g for g, p in data['plot_features'] if p.get('source_id') == 'way/178737608' and p['geometry_role'] == 'INDEPENDENT_NATIVE_SOURCE_LINE')
    draw_geometry(lower, native_link, edge=P2['ink'], width=1.6, zorder=28)
    for number, offset in [(1890935415, (-94, -42)), (1891590997, (18, 25))]:
        g = next(g for g, p in data['plot_features'] if p.get('id') == f'node/{number}') if any(p.get('id') == f'node/{number}' for g, p in data['plot_features']) else None
        if g is None:
            # Node coordinates are already present on the original three-node line.
            line_row = next(p for _, p in data['plot_features'] if p.get('source_id') == 'way/178737608' and p['geometry_role'] == 'INDEPENDENT_NATIVE_SOURCE_LINE')
            g = Point(list(native_link.coords)[line_row['nodes'].index(number)])
        lower.plot(g.x, g.y, marker='o', color=P2['ink'], markerfacecolor=P2['paper'], markersize=4, zorder=29)
        label(lower, g.coords[0], f'node/{number}', offset, size=7)
    fig.suptitle('博物馆步行面与东北侧步道：原始几何能够说明什么', x=.065, y=.98, ha='left', fontsize=16)
    fig.text(.065, .927, '原边界保持不变；已有线端接边与非零间隙分开判断。截图请求尚未唯一绑定。', fontsize=10, color=P2['muted'])
    fig.legend(handles=legend_handles(), loc='lower left', bbox_to_anchor=(.06, .075), ncol=4, frameon=False, fontsize=8)
    fig.text(.065, .026, 'EPSG:32651 · 点线表示真实源几何与距离测量，不是补画接缝。© OpenStreetMap contributors / ODbL · 冻结源 2026-11-08', fontsize=8, color=P2['muted'])
    return save(fig, 'museum_source_overview', {'question': '区分南门面与周围步道的真实接触和超过阈值的源间隙',
        'scene_id': 'sh-huangpu-01', 'source_sha256': data['source_clip_sha256'],
        'face_pair': ['relation/2385771', 'relation/2153738'], 'P_face_distance_m': face_gap.length,
        'northeast_line_id': 'way/564255372', 'P_line_distance_m': line_gap.length,
        'existing_native_connection': {'way_id': 'way/178737608', 'face_shared_node_id': 'node/1890935415', 'line_shared_node_id': 'node/1891590997', 'source_topology_connected_via_independent_line': True, 'routing_graph_admission': 'CHECK_FORMAL_ROUTE_EVIDENCE; RAW_SOURCE_CHAIN_DOES_NOT_PROVE_WHOLE_GRAPH_PASSABILITY'},
        'screenshot_binding': 'SCREENSHOT_REQUEST_UNBOUND', 'user_observation': 'PENDING_USER_OBSERVATION',
        'layout_choice': 'OVERVIEW_PLUS_TWO_MECHANISM_DETAILS; A_SINGLE_FULL_MAP_MAKES_7M_AND_10M_GAPS_UNREADABLE'})


def source_distribution_map():
    manifest = read(ROOT / 'data/scene_manifest.json')
    fig, axes = plt.subplots(2, 3, figsize=(15, 10.7))
    fig.subplots_adjust(left=.065, right=.985, bottom=.16, top=.87, wspace=.25, hspace=.36)
    rows = []
    for i, (ax, scene) in enumerate(zip(axes.flat, manifest['scenes'])):
        data = load_scene(scene['scene_id']); summary = data['source_population']
        coverage = shape(summary['coverage_geometry'])
        draw_scene(ax, data, trim_extent(coverage.bounds, ratio=1.25), face_width=1.5,
                   context_alpha=.5, rasterize_background=True)
        legal = sum(p.get('status') == 'ADMITTED' for _, p in data['plot_features'] if p['geometry_role'] == 'LEGAL_OMEGA')
        ax.set_title(f"{chr(97 + i)}  {scene['label']}\n旧 {summary['old_count']} → 源完整 {summary['selected_count']}；新增 {summary['added_count']}，Ω 非空 {legal}", loc='left', fontsize=10, pad=8)
        building = next((g for g, p in data['plot_features'] if p.get('id') == scene['building_native_id']), None)
        if building is not None:
            ax.plot(building.centroid.x, building.centroid.y, marker='+', color=P2['ink'], markersize=8, zorder=40)
        rows.append({'scene_id': scene['scene_id'], 'source_sha256': scene['source_sha256'],
            'old_count': summary['old_count'], 'selected_count': summary['selected_count'],
            'added_count': summary['added_count'], 'nonempty_omega_count': legal, 'bounds': list(coverage.bounds)})
        diagnosis_data.cache_clear()
    fig.suptitle('六个冻结裁片：旧选面没有代表全部原生步行面', x=.065, y=.975, ha='left', fontsize=17)
    fig.text(.065, .928, '130 个场景面记录 / 88 个原生面；124 个场景新增记录对应 82 个此前从未选入的原生面。跨片副本不构成独立证据。', fontsize=10, color=P2['muted'])
    fig.legend(handles=legend_handles(), loc='lower left', bbox_to_anchor=(.06, .055), ncol=4, frameon=False, fontsize=8)
    fig.text(.065, .023, '面积仅取明确步行面标签、完整成员、地面/权限及真实覆盖合格者；公园与草地保持独立背景。+ 为场景目标建筑。© OSM contributors / ODbL · 2026-11-08', fontsize=8, color=P2['muted'])
    return save(fig, 'six_scene_source_distribution', {'question': '全部显式源面在六个既有冻结裁片中的分布与旧集合遗漏',
        'scenes': rows, 'denominator': 'SCENE_ID_OBJECT_COUNT_WITH_GLOBAL_UNIQUE_COUNTS_SEPARATELY_REPORTED',
        'global_unique_source_faces': 88, 'scene_id_source_faces': 130, 'new_global_unique_source_faces': 82,
        'background_export': 'DENSE_RAW_CONTEXT_RASTERIZED_AT_300DPI_IN_VECTOR_EXPORTS; P_OMEGA_NATIVE_LINES_AND_AXES_REMAIN_VECTOR; SOURCE_GEOMETRY_UNALTERED'})


def source_inventory():
    manifest = read(ROOT / 'data/scene_manifest.json')
    summaries = [read(ROOT / 'data/connectivity' / f"{scene['scene_id']}_inventory_summary.json") for scene in manifest['scenes']]
    categories = [
        ('旧集合且源准入', 'old_count', P2['blue_accent']),
        ('旧数据遗漏、源准入', 'added_count', P2['violet_accent']),
        ('非地面 / 层级拒绝', 'NON_GROUND_OR_UNRESOLVED_LAYER', P2['rose_accent']),
        ('源覆盖不完整拒绝', 'INCOMPLETE_SOURCE_COVERAGE', P2['apricot_accent'])]
    values = [[summary[key] if key in summary else summary['rejected_explicit_reasons'].get(key, 0)
               for summary in summaries] for _, key, _ in categories]
    for i, summary in enumerate(summaries):
        if sum(category[i] for category in values) != summary['explicit_source_candidate_count']:
            raise ValueError('SOURCE_COUNT_PARTITION_NOT_CONSERVED')
    fig, ax = plt.subplots(figsize=(12.8, 6.5))
    fig.subplots_adjust(left=.26, right=.77, bottom=.25, top=.79)
    lefts = [0] * 6
    for (name, _, color), counts in zip(categories, values):
        bars = ax.barh(range(6), counts, left=lefts, height=.56, color=color, edgecolor=P2['paper'], linewidth=.9, label=name)
        for i, (bar, count) in enumerate(zip(bars, counts)):
            if count >= 2:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_y() + bar.get_height() / 2,
                    str(count), va='center', ha='center', color=P2['paper'], fontsize=9, fontweight='bold')
            lefts[i] += count
    ax.set_yticks(range(6), [scene['label'] for scene in manifest['scenes']]); ax.invert_yaxis()
    ax.set_xlim(0, 57); ax.set_xticks(range(0, 60, 10)); ax.set_xlabel('显式源候选数（场景—对象记录）', labelpad=9)
    ax.set_axisbelow(True); ax.xaxis.grid(True, color=P2['rule'], linewidth=.6)
    for name in ('top', 'right', 'left'):
        ax.spines[name].set_visible(False)
    ax.tick_params(axis='y', length=0, labelsize=10, pad=12)
    for i, summary in enumerate(summaries):
        faces = read(ROOT / 'data/connectivity' / f"{summary['scene_id']}_faces.json")
        omega_count = sum(face['status'] == 'ADMITTED' for face in faces)
        ax.text(1.05, i, f"{summary['selected_count']} / {omega_count}", transform=ax.get_yaxis_transform(), ha='center', va='center', fontsize=10)
        ax.text(summary['explicit_source_candidate_count'] + .5, i, str(summary['explicit_source_candidate_count']), va='center', fontsize=9, color=P2['muted'])
    ax.text(1.05, -.84, '源准入 / Ω 非空', transform=ax.get_yaxis_transform(), ha='center', fontsize=10)
    fig.suptitle('六个冻结裁片：补齐源面，同时保留拒绝原因', x=.065, y=.97, ha='left', fontsize=17)
    fig.text(.065, .895, '149 个显式步行面候选 = 旧准入 6 + 新增准入 124 + 层级拒绝 7 + 覆盖拒绝 12', fontsize=11)
    fig.text(.065, .845, '准入的 130 个场景面按 type/id、version、源时间戳去重为 88 个原生面，其中此前未选入者为 82 个。', fontsize=9.5, color=P2['muted'])
    fig.legend(handles=[Patch(facecolor=color, label=name) for name, _, color in categories],
               loc='lower left', bbox_to_anchor=(.06, .115), ncol=4, frameon=False, fontsize=9)
    fig.text(.065, .07, '上海中心 way/166128036 原始面合格，扣障后 Ω 为空；不填回限制。公园、草地没有被一律纳入步行面。', fontsize=9, color=P2['muted'])
    fig.text(.065, .025, '© OpenStreetMap contributors / ODbL · 六份既有冻结裁片 · 2026-11-08T21:21:00Z · 跨裁片副本不作为独立面积证据', fontsize=8, color=P2['muted'])
    return save(fig, 'six_scene_source_inventory', {'question': '按互斥来源原因完整核对六场景候选人口，避免跨clip重复当独立证据',
        'scenes': [{'scene_id': s['scene_id'], 'old': values[0][i], 'new': values[1][i], 'non_ground_rejected': values[2][i],
                    'coverage_rejected': values[3][i], 'explicit_candidate_count': s['explicit_source_candidate_count']} for i, s in enumerate(summaries)],
        'partition_total': 149, 'partition_conserved': True, 'source_admitted_scene_id_count': 130,
        'global_unique_source_faces': 88, 'new_global_unique_source_faces': 82,
        'layout_choice': 'MUTUALLY_EXCLUSIVE_COUNT_BARS_SELECTED_AFTER_RENDER_REVIEW; FULL_CLIP_GALLERY_IS_TOO_DENSE_AT_FINAL_SIZE',
        'full_source_geography': 'AVAILABLE_IN_INTERACTIVE_SIX_SCENE_DIAGNOSIS_AND_ROUTE_CASE_MAPS'})


def result_segments(result):
    if result.get('working_crs') not in (None, 'EPSG:32651'):
        raise ValueError('ROUTE_RESULT_NOT_METRIC_32651')
    return result.get('route', {}).get('segments', [])


def result_endpoints(result):
    """Preserve source query identities and exact coordinates in plot evidence."""
    query = result.get('query', {})
    if query:
        return [query['start'], query['end']]
    start = result.get('start', {})
    return [{'id': start.get('id'), 'xy': start.get('network_xy'),
             'raw_xy': start.get('raw_xy')}, result.get('door', {})]


def draw_result(ax, result, *, old=False):
    color = P2['rose_accent'] if old else P2['ink']
    assumed = result.get('planning_region', {}).get('assumed')
    if assumed:
        draw_geometry(ax, shape(assumed), face=P2['apricot'], edge=P2['apricot_accent'],
                      width=.4, alpha=.45, hatch='//', zorder=4)
    for segment in result_segments(result):
        xy = segment['xy']
        conditional = segment.get('geometry_kind') in {'CONDITIONAL_GAP_LINK', 'CONDITIONAL_GAP_PATCH'}
        door_assumed = not conditional and segment.get('layer') in {'inferred', 'assumed', 'unknown'}
        ax.plot([p[0] for p in xy], [p[1] for p in xy], color=P2['apricot_accent'] if conditional or door_assumed else color,
            linestyle='--' if conditional else 'dotted' if door_assumed else '--' if old else 'solid',
            linewidth=2.4 if conditional or door_assumed else 1.9,
            zorder=32 if conditional else 30, path_effects=[patheffects.Stroke(linewidth=3.4, foreground=P2['paper']), patheffects.Normal()])
    evidence = result.get('connectivity_evidence', {})
    route_nodes = {s[k] for s in result_segments(result) for k in ('u', 'v') if k in s}
    for portal in [*result.get('face_network', {}).get('portals', []), *evidence.get('stitch_portals', [])]:
        if portal['id'] in route_nodes:
            ax.plot(*portal['xy'], marker='o', color=P2['apricot_accent'] if portal['id'].startswith('stitch/seam/') else P2['blue_accent'], markerfacecolor=P2['paper'], markersize=3.2, zorder=34)
    for candidate in evidence.get('seams', evidence.get('conditional_links', [])):
        if candidate.get('geometry'):
            accepted = candidate.get('accepted', False)
            draw_geometry(ax, shape(candidate['geometry']), edge=P2['apricot_accent'] if accepted else P2['rose_accent'],
                          width=1.1, dash='dotted', alpha=.65 if accepted else .3, zorder=15)


def draw_query_endpoints(ax, result, label_offsets=None):
    query = result.get('query', {})
    mechanism = bool(query)
    endpoints = result_endpoints(result)
    for i, endpoint in enumerate(endpoints):
        xy = endpoint.get('xy')
        if xy is None:
            continue
        marker = '^' if i == 0 else 'D' if mechanism else 's'
        ax.plot(*xy, marker=marker, markersize=5, markeredgewidth=1.1,
            color=P2['ink'], markerfacecolor=P2['ink'] if i == 0 else P2['paper'], zorder=39)
        if mechanism:
            kind = '源边界起点' if i == 0 and endpoint.get('source_area_id') else '机制起点' if i == 0 else '机制终点（非门）'
        else:
            kind = '同一原生起点' if i == 0 else '原登记出口（仅到门外）' if endpoint.get('tags', {}).get('entrance') == 'exit' else '原登记门'
        offset = (-112, 9 if i == 0 else -28) if xy[0] > sum(ax.get_xlim()) / 2 else (7, 9 if i == 0 else -28)
        offset = (label_offsets or {}).get(endpoint.get('id'), offset)
        label(ax, xy, f"{kind}\n{endpoint.get('id', '')}", offset, size=7.2)


def route_comparison(spec):
    scene_id = spec['scene_id']; data = load_scene(scene_id)
    paths = [ROOT / spec['old_result'], ROOT / spec['new_result']]
    results = [read(p) for p in paths]
    old_request, new_request = [r.get('normalized_request', r.get('input', {})) for r in results]
    for field in ('scene_id', 'start_id', 'door_id', 'purpose', 'method'):
        if field in old_request and field in new_request and old_request[field] != new_request[field]:
            raise ValueError('COMPARISON_REQUEST_MISMATCH:' + field)
    endpoints = [result_endpoints(result) for result in results]
    endpoint_controls = [[(p.get('id'), p.get('xy')) for p in row] for row in endpoints]
    if endpoint_controls[0] != endpoint_controls[1]:
        raise ValueError('COMPARISON_SOURCE_ENDPOINT_ID_OR_COORDINATE_MISMATCH')
    coordinates = [p for result in results for segment in result_segments(result) for p in segment['xy']]
    if 'bounds' in spec:
        bounds = trim_extent(spec['bounds'], ratio=1.1)
    elif coordinates:
        xs, ys = zip(*coordinates); bounds = trim_extent([min(xs), min(ys), max(xs), max(ys)], ratio=1.1, padding=18)
    else:
        raise ValueError('NO_ROUTE_GEOMETRY: EXPLICIT_SOURCE_BOUNDS_REQUIRED_FOR_REJECTION_FIGURE')
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 7.6))
    fig.subplots_adjust(left=.07, right=.98, bottom=.30, top=.79, wspace=.18)
    for ax, result, is_old in zip(axes, results, [True, False]):
        draw_scene(ax, data, bounds)
        draw_result(ax, result, old=is_old)
        draw_query_endpoints(ax, result, spec.get('endpoint_label_offsets'))
        query = result.get('query', {})
        for field in ('a_source_id', 'b_source_id'):
            source_id = query.get(field)
            source_polygon = next((g for g, p in data['plot_features'] if p.get('source_id') == source_id and p['geometry_role'] == 'SOURCE_P'), None)
            if source_polygon is not None:
                visible = source_polygon.intersection(box(*bounds))
                if not visible.is_empty:
                    offset = spec.get('source_label_offsets', {}).get(source_id, [7, -15])
                    label(ax, visible.representative_point().coords[0], source_id, offset, color=P2['violet_accent'], size=7)
        mode = result.get('input', {}).get('connectivity_mode', result.get('connectivity_mode', 'UNKNOWN'))
        profile = result.get('method', result.get('input', {}).get('method', 'UNKNOWN'))
        threshold = result.get('normalized_request', {}).get('seam_max_m', result.get('input', {}).get('seam_max_m'))
        if mode == 'CONDITIONAL_SEAMS' and threshold is not None:
            mode += f" (δ≤{threshold:g} m)"
        route = result.get('route', {})
        metrics = f"L={route['length_m']:.2f} m · C={route['cost_weighted_m']:.2f} m" if route else '未形成完整路线'
        ax.set_title(f"{'a  对照模式' if is_old else 'b  比较模式'} · {mode} / {profile}\n{result['status']} · {metrics}", loc='left', fontsize=9.2)
        if not result_segments(result):
            failure = result.get('failure', {}).get('code', result['status'])
            ax.text(.5, .5, ('图不连通\n' if failure == 'DISCONNECTED_GRAPH' else '') + failure, transform=ax.transAxes,
                    ha='center', va='center', color=P2['rose_accent'], fontsize=10,
                    bbox={'facecolor': P2['paper'], 'edgecolor': 'none', 'alpha': .94})
        run_label = result.get('run_id', 'NO_RUN_ID')
        ax.text(0, -.20, run_label, transform=ax.transAxes, fontsize=6.2, color=P2['muted'])
    seam_detail = None
    source_interface_detail = None
    assumed_detail = None
    if spec.get('assumed_detail'):
        assumed_segments = [s for s in result_segments(results[1]) if s.get('layer') in {'inferred', 'assumed', 'unknown'}
            and s.get('geometry_kind') not in {'CONDITIONAL_GAP_LINK', 'CONDITIONAL_GAP_PATCH'}]
        if not assumed_segments:
            raise ValueError('REQUESTED_DOOR_ASSUMPTION_DETAIL_HAS_NO_REAL_SEGMENTS')
        geometry = unary_union([LineString(s['xy']) for s in assumed_segments])
        detail_options = spec['assumed_detail'] if isinstance(spec['assumed_detail'], dict) else {}
        inset = axes[1].inset_axes(detail_options.get('rect', [.61, .21, .36, .32]))
        draw_scene(inset, data, trim_extent(geometry.bounds, ratio=1.5, padding=3), face_width=1)
        draw_result(inset, results[1])
        inset.set_xticks([]); inset.set_yticks([]); inset.set_xlabel(''); inset.set_ylabel('')
        for text in list(inset.texts):
            if text.get_text() == '网格北':
                text.remove()
        length = sum(s['length_m'] for s in assumed_segments)
        inset.set_title(f'原门前假设段 {length:.2f} m\n原先已存在，不是本轮接缝', fontsize=7, pad=3)
        assumed_detail = {'length_m': length, 'source': 'ACTUAL_NON_SEAM_HYPOTHESIS_ROUTE_SEGMENTS',
                          'new_conditional_seam_claim': False}
    if spec.get('source_interface_detail'):
        wanted = spec['source_interface_detail']
        raw_line, line_props = next((g, p) for g, p in data['plot_features']
            if p.get('source_id') == wanted['source_line_id'] and p['geometry_role'] == 'INDEPENDENT_NATIVE_SOURCE_LINE')
        number = int(wanted['native_node_id'].split('/')[1])
        point = Point(list(raw_line.coords)[line_props['nodes'].index(number)])
        pgeom = next(g for g, p in data['plot_features'] if p.get('source_id') == wanted['source_area_id'] and p['geometry_role'] == 'SOURCE_P')
        omega = next(g for g, p in data['plot_features'] if p.get('source_id') == wanted['source_area_id'] and p['geometry_role'] == 'LEGAL_OMEGA')
        inset = axes[1].inset_axes([.57, .04, .40, .32])
        draw_scene(inset, data, trim_extent(point.buffer(7).bounds, ratio=1.5), face_width=1.1)
        draw_result(inset, results[1])
        inset.plot(point.x, point.y, marker='o', markeredgecolor=P2['blue_accent'], markerfacecolor=P2['paper'], markersize=4, zorder=42)
        inset.set_xticks([]); inset.set_yticks([]); inset.set_xlabel(''); inset.set_ylabel('')
        for text in list(inset.texts):
            if text.get_text() == '网格北':
                text.remove()
        inset.set_title(wanted.get('title', '原生共享节点接边'), fontsize=7, pad=3)
        inset.text(.025, .975, wanted['source_line_id'] + '\n' + wanted['native_node_id'],
            transform=inset.transAxes, ha='left', va='top', fontsize=6,
            bbox={'facecolor': P2['paper'], 'edgecolor': 'none', 'alpha': .95, 'pad': 1}, zorder=43)
        old_nodes = {s[k] for s in result_segments(results[0]) for k in ('u', 'v') if k in s}
        new_nodes = {s[k] for s in result_segments(results[1]) for k in ('u', 'v') if k in s}
        source_interface_detail = {'source_area_id': wanted['source_area_id'], 'source_line_id': wanted['source_line_id'],
            'native_node_id': wanted['native_node_id'], 'xy': list(point.coords[0]),
            'P_distance_m': pgeom.distance(point), 'omega_distance_m': omega.distance(point),
            'node_used_in_old_route': wanted['native_node_id'] in old_nodes,
            'node_used_in_new_route': wanted['native_node_id'] in new_nodes, 'new_interface_claim': False}
    if spec.get('seam_detail'):
        wanted = spec['seam_detail']
        pool = [r for r in results[1].get('connectivity_evidence', {}).get('seams', []) if r.get('accepted')
                and wanted['source_area_id'] in r.get('source_area_ids', []) and wanted['source_id'] in r.get('source_ids', [])]
        if not pool:
            raise ValueError('NO_SAVED_ACCEPTED_SEAM_FOR_REQUESTED_DETAIL')
        record = sorted(pool, key=lambda r: r['id'])[0]
        geometry = shape(record['geometry'])
        inset = axes[1].inset_axes([.58, .045, .39, .31])
        draw_scene(inset, data, trim_extent(geometry.bounds, ratio=1.5, padding=2), face_width=1)
        draw_result(inset, results[1])
        draw_geometry(inset, geometry, edge=P2['apricot_accent'], width=2.3, dash='dashed', zorder=40)
        inset.set_xticks([]); inset.set_yticks([]); inset.set_xlabel(''); inset.set_ylabel('')
        for text in list(inset.texts):
            if text.get_text() == '网格北':
                text.remove()
        used = record['id'] in results[1].get('route', {}).get('interface_ids_used', [])
        inset.set_title(f"{record['distance_m']:.2f} m 已入图；{'路线使用' if used else '本路线未用'}", fontsize=7, pad=3)
        seam_detail = {'id': record['id'], 'distance_m': record['distance_m'],
                       'entered_graph': record.get('entered_graph'), 'used_by_displayed_route': used}
    fig.suptitle(spec.get('title', spec['id']), x=.07, y=.97, ha='left', fontsize=16)
    fig.text(.07, .916, '同一端点与视野；底图统一显示完整源 P/Ω，路线分别取各模式真实求解输出。', fontsize=10, color=P2['muted'])
    if spec.get('note'):
        fig.text(.07, .874, spec['note'], fontsize=9, color=P2['violet_accent'])
    if spec.get('epoch_note'):
        fig.text(.07, .851, spec['epoch_note'], fontsize=6.2, color=P2['muted'])
    fig.legend(handles=legend_handles(routes=True), loc='lower left', bbox_to_anchor=(.065, .057), ncol=4, frameon=False, fontsize=7.5)
    fig.text(.07, .022, 'L：几何长度；C：广义代价。橙色虚线为条件接缝假设，原边界未移动。EPSG:32651 · © OpenStreetMap contributors / ODbL · 2026-11-08', fontsize=8, color=P2['muted'])
    return save(fig, spec['id'], {'question': spec.get('title', spec['id']), 'scene_id': scene_id,
        'source_sha256': data['source_clip_sha256'], 'bounds': bounds,
        'saved_results': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha256(p.read_bytes()).hexdigest(),
            'run_id': r.get('run_id'), 'solver': r.get('solver'), 'status': r['status'],
            'route_length_m': r.get('route', {}).get('length_m'),
            'route_cost_weighted_m': r.get('route', {}).get('cost_weighted_m'),
            'endpoints': result_endpoints(r),
            'code_sha256': r.get('versions', {}).get('code_sha256'),
            'input_connectivity_mode': r.get('input', {}).get('connectivity_mode'),
            'raw_evidence_parent_mode': r.get('connectivity_evidence', {}).get('parent_mode'),
            'preprocessing_cache_key': r.get('preprocessing_cache', {}).get('key'),
            'unweighted_graph_sha256': r.get('versions', {}).get('unweighted_graph_sha256', r.get('graph', {}).get('unweighted_sha256')),
            'source_sha256': r.get('versions', {}).get('source', {}).get('source_sha256', data['source_clip_sha256'])}
            for p, r in zip(paths, results)],
        'same_base_and_extent': True, 'same_exact_source_endpoints': True,
        'route_coordinates_altered': False, 'seam_detail': seam_detail,
        'assumed_detail': assumed_detail,
        'same_full_route_segment_geometries': ([s['xy'] for s in result_segments(results[0])] == [s['xy'] for s in result_segments(results[1])])
            if result_segments(results[0]) and result_segments(results[1]) else None,
        'new_exact_or_seam_length_m': sum(s['length_m'] for s in result_segments(results[1])
            if s.get('geometry_kind') in {'SOURCE_SUPPORTED_INTERFACE', 'CONDITIONAL_GAP_LINK', 'CONDITIONAL_GAP_PATCH'}),
        'new_source_area_ids_used': sorted({sid for s in result_segments(results[1])
            for sid in [s.get('source_area_id', s.get('source_id')), *s.get('source_area_ids', [])]
            if sid in data['source_population']['added_area_ids']}),
        'source_interface_detail': source_interface_detail,
        'epoch_compatibility_note': spec.get('epoch_note'),
        'mode_authority': 'ACTUAL_RESULT_INPUT_MODE; RAW_PARENT_MODE_IS_PRESERVED_METADATA_ONLY; PREP_CHAIN_REMAINS_EXTERNAL_AUTHORITY'})


def check_exports():
    """One fresh PDF renderer per document avoids shared font-subset caches."""
    from PIL import Image, ImageStat, ImageChops
    checks = ROOT / 'figures/visuals/render_checks'
    checks.mkdir(parents=True, exist_ok=True)
    rows = []
    for pdf in sorted(OUT.glob('*.pdf')):
        png = pdf.with_suffix('.png'); metadata = read(pdf.with_suffix('.json'))
        expected = {Path(r['path']).name: r['sha256'] for r in metadata['outputs']}
        for path in (pdf, png, pdf.with_suffix('.svg')):
            if sha256(path.read_bytes()).hexdigest() != expected[path.name]:
                raise ValueError('EXPORTED_FIGURE_IDENTITY_CHANGED:' + path.name)
        rendered = checks / png.name
        code = "import fitz,sys; d=fitz.open(sys.argv[1]); assert len(d)==1; p=d[0].get_pixmap(dpi=200,alpha=False); p.save(sys.argv[2]); d.close()"
        subprocess.run([sys.executable, '-B', '-c', code, str(pdf), str(rendered)], check=True,
                       capture_output=True, text=True)
        with Image.open(png) as image:
            width, height = image.size
            thumbnail = image.convert('RGB'); thumbnail.thumbnail((256, 256))
            stddev = sum(ImageStat.Stat(thumbnail).stddev) / 3
            actual = Image.open(rendered).convert('RGB')
            resized = image.convert('RGB').resize(actual.size)
            difference = sum(ImageStat.Stat(ImageChops.difference(resized, actual)).mean) / 3
        if min(width, height) < 1000 or max(width, height) < 1600 or stddev < 3:
            raise ValueError('UNDERSIZED_OR_BLANK_EXPORT:' + png.name)
        rows.append({'figure': pdf.stem, 'png_pixels': [width, height], 'channel_stddev': stddev,
            'pdf_render_dpi': 200, 'pdf_render_pixels': list(actual.size),
            'png_vs_pdf_mean_absolute_channel_difference': difference,
            'pdf_renderer': 'PyMuPDF_FRESH_PROCESS_PER_DOCUMENT',
            'rendered_page': rendered.relative_to(ROOT).as_posix(),
            'dimensions_blank_and_hash_checks_passed': True,
            'author_visual_review': 'PENDING_ACTUAL_IMAGE_INSPECTION'})
    (OUT / 'exports_qa.json').write_text(json.dumps({'role': 'AUTHOR_EXPORT_QA_NOT_INDEPENDENT_REVIEW',
        'checks': rows, 'solver_calls': 0, 'external_requests': 0}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'export_qa': rows}, ensure_ascii=False))


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--comparison-spec', type=Path)
    parser.add_argument('--check-exports', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=OUT)
    args = parser.parse_args()
    OUT = (ROOT / args.output_dir).resolve()
    if not OUT.is_relative_to(ROOT):
        raise ValueError('FIGURE_OUTPUT_DIRECTORY_MUST_BE_INSIDE_PROJECT')
    theme(); outputs = []
    if args.check_exports and not args.source_only and not args.comparison_spec:
        check_exports(); return
    if args.source_only or not args.comparison_spec:
        outputs.extend(museum_source()); diagnosis_data.cache_clear()
        outputs.extend(source_inventory())
    if args.comparison_spec:
        for spec in read(args.comparison_spec)['cases']:
            outputs.extend(route_comparison(spec)); diagnosis_data.cache_clear()
    if args.check_exports:
        check_exports()
    print(json.dumps({'outputs': outputs, 'solver_calls': 0, 'external_requests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
