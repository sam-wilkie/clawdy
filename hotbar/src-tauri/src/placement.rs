#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// Transparent CSS margin: only the docked side may overhang the work area.
pub const EDGE_MARGIN: f64 = 12.;
#[derive(Clone, Copy, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Edge { Left, Right, Top, Bottom }
impl Edge {
    pub fn vertical(self) -> bool { matches!(self, Self::Left | Self::Right) }
}
/// `extra` is the logical height custom cells add to (or hidden agents take from) the expanded bar.
pub fn bar_size(edge: Edge, collapsed: bool, scale: f64, extra: f64) -> (f64, f64) {
    let span = if collapsed { 156. } else { 466. + extra } * scale;
    if edge.vertical() { (82. * scale, span) } else { (span, 82. * scale) }
}
pub fn monitor_index(bar: Rect, areas: &[Rect]) -> Option<usize> {
    let (x, y) = (bar.x + bar.width / 2., bar.y + bar.height / 2.);
    areas.iter().position(|a| x >= a.x && x < a.x + a.width && y >= a.y && y < a.y + a.height)
}
pub fn nearest_edge(bar: Rect, area: Rect) -> Edge {
    let (x, y) = (bar.x + bar.width / 2., bar.y + bar.height / 2.);
    [(Edge::Left, (x - area.x).abs()), (Edge::Right, (area.x + area.width - x).abs()),
        (Edge::Top, (y - area.y).abs()), (Edge::Bottom, (area.y + area.height - y).abs())]
        .into_iter().min_by(|a, b| a.1.total_cmp(&b.1)).unwrap().0
}
/// Preserve the along-edge origin, clamping it when the requested span no longer fits.
pub fn dock(bar: Rect, edge: Edge, collapsed: bool, area: Rect, scale: f64, extra: f64) -> Rect {
    let (width, height) = bar_size(edge, collapsed, scale, extra);
    let (width, height) = (width.min(area.width), height.min(area.height));
    let over = EDGE_MARGIN * scale;
    let mut r = Rect { x: bar.x.clamp(area.x, area.x + area.width - width),
        y: bar.y.clamp(area.y, area.y + area.height - height), width, height };
    match edge {
        Edge::Left => r.x = area.x - over,
        Edge::Right => r.x = area.x + area.width - width + over,
        Edge::Top => r.y = area.y - over,
        Edge::Bottom => r.y = area.y + area.height - height + over,
    }
    r
}
pub fn restore(saved: Option<(f64, f64)>, edge: Option<Edge>, collapsed: bool,
               monitors: &[(Rect, Rect, f64)], primary: (Rect, f64), extra: f64) -> (Rect, Edge) {
    if let Some((x, y)) = saved {
        for &(bounds, a, scale) in monitors {
            let (width, height) = bar_size(edge.unwrap_or(Edge::Right), collapsed, scale, extra);
            let r = Rect { x, y, width: width.min(a.width), height: height.min(a.height) };
            if monitor_index(r, &[bounds]).is_some() {
                let edge = edge.unwrap_or_else(|| nearest_edge(r, a));
                return (dock(r, edge, collapsed, a, scale, extra), edge);
            }
        }
    }
    let (a, scale) = primary;
    let (_, height) = bar_size(Edge::Right, collapsed, scale, extra);
    (dock(Rect { y: a.y + (a.height - height.min(a.height)) / 2., ..a },
        Edge::Right, collapsed, a, scale, extra), Edge::Right)
}
pub fn panel_side(bar: Rect, size: (f64, f64), area: Rect, edge: Edge) -> Rect {
    let (width, height) = (size.0.min(area.width), size.1.min(area.height));
    let (x, y) = match edge {
        Edge::Left => (bar.x + bar.width + 8., bar.y),
        Edge::Right => (bar.x - width - 8., bar.y),
        Edge::Top => (bar.x, bar.y + bar.height + 8.),
        Edge::Bottom => (bar.x, bar.y - height - 8.),
    };
    Rect { x: x.clamp(area.x, area.x + area.width - width),
        y: y.clamp(area.y, area.y + area.height - height), width, height }
}

#[cfg(test)]
mod tests {
    use super::*;
    const AREA: Rect = Rect { x: 0., y: 0., width: 1920., height: 1040. };
    const LEFT: Rect = Rect { x: -1280., y: -200., width: 1280., height: 1024. };
    fn bar(x: f64, y: f64) -> Rect { Rect { x, y, width: 82., height: 466. } }
    #[test]
    fn nearest_edges_include_negative_and_secondary_monitors() {
        for (x, y, edge) in [(0., 200., Edge::Left), (1800., 200., Edge::Right),
            (900., -200., Edge::Top), (900., 800., Edge::Bottom)] {
            assert_eq!(nearest_edge(bar(x, y), AREA), edge);
        }
        assert_eq!(monitor_index(bar(-1200., -100.), &[AREA, LEFT]), Some(1));
        assert_eq!(nearest_edge(bar(-1200., -100.), LEFT), Edge::Left);
        assert_eq!(monitor_index(bar(3000., 0.), &[AREA, LEFT]), None);
    }
    #[test]
    fn dock_is_flush_and_collapse_keeps_the_along_edge_origin() {
        for edge in [Edge::Left, Edge::Right, Edge::Top, Edge::Bottom] {
            for scale in [1., 1.25, 2.] {
                let expanded = dock(bar(200., 100.), edge, false, AREA, scale, 0.);
                let collapsed = dock(expanded, edge, true, AREA, scale, 0.);
                assert_eq!((expanded.width, expanded.height), bar_size(edge, false, scale, 0.));
                assert_eq!(dock(collapsed, edge, false, AREA, scale, 0.), expanded);
                let over = EDGE_MARGIN * scale;
                match edge {
                    Edge::Left => assert_eq!(expanded.x + over, AREA.x),
                    Edge::Right => assert_eq!(expanded.x + expanded.width - over, AREA.width),
                    Edge::Top => assert_eq!(expanded.y + over, AREA.y),
                    Edge::Bottom => assert_eq!(expanded.y + expanded.height - over, AREA.height),
                }
                if edge.vertical() { assert_eq!(expanded.y, collapsed.y); }
                else { assert_eq!(expanded.x, collapsed.x); }
                assert_eq!(bar_size(edge, true, scale, 0.), if edge.vertical() {
                    (82. * scale, 156. * scale)
                } else { (156. * scale, 82. * scale) });
            }
        }
        assert_eq!(dock(bar(-1300., 700.), Edge::Left, false, LEFT, 1., 0.), bar(-1292., 358.));
        assert_eq!(dock(bar(1800., 900.), Edge::Top, false, AREA, 1., 0.).x, 1454.);
    }
    #[test]
    fn restore_defaults_removed_monitor_legacy_and_saved_edge() {
        let monitors = [(AREA, AREA, 1.), (LEFT, LEFT, 2.)];
        for saved in [None, Some((3000., 0.))] {
            assert_eq!(restore(saved, Some(Edge::Top), false, &monitors, (AREA, 1.), 0.),
                (bar(1850., 287.), Edge::Right));
        }
        assert_eq!(restore(Some((-1200., -100.)), None, false, &monitors, (AREA, 1.), 0.).1, Edge::Left);
        for edge in [Edge::Left, Edge::Right, Edge::Top, Edge::Bottom] {
            let rect = dock(bar(-1000., -100.), edge, true, LEFT, 2., 0.);
            assert_eq!(restore(Some((rect.x, rect.y)), Some(edge), true, &monitors, (AREA, 1.), 0.), (rect, edge));
        }
        let full = Rect { height: 1200., ..AREA };
        assert_eq!(restore(Some((700., 1060.)), None, true, &[(full, AREA, 1.)], (AREA, 1.), 0.).1, Edge::Bottom);
        let (rect, edge) = restore(Some((700., 0.)), Some(Edge::Bottom), true, &monitors, (AREA, 1.), 0.);
        assert_eq!(edge, Edge::Bottom);
        assert_eq!(rect, Rect { x: 700., y: 970., width: 156., height: 82. });
    }
    #[test]
    fn extra_height_resizes_only_the_expanded_span_and_stays_flush() {
        assert_eq!(bar_size(Edge::Right, false, 1.5, 100.), (82. * 1.5, 566. * 1.5));
        assert_eq!(bar_size(Edge::Bottom, false, 1., -50.), (416., 82.));
        assert_eq!(bar_size(Edge::Right, true, 1.5, 100.), bar_size(Edge::Right, true, 1.5, 0.));
        let grown = dock(bar(1800., 100.), Edge::Right, false, AREA, 1., 100.);
        assert_eq!((grown.width, grown.height), (82., 566.));
        assert_eq!(grown.x + grown.width - EDGE_MARGIN, AREA.width);
        let (rect, _) = restore(None, None, false, &[], (AREA, 1.), 100.);
        assert_eq!(rect.height, 566.);
    }
    #[test]
    fn panels_face_inward_and_clamp_in_tight_areas() {
        let bar = Rect { x: 800., y: 800., width: 82., height: 466. };
        let area = Rect { width: 3000., height: 2500., ..AREA };
        for (edge, x, y) in [(Edge::Left, 890., 800.), (Edge::Right, 384., 800.),
            (Edge::Top, 800., 1274.), (Edge::Bottom, 800., 126.)] {
            assert_eq!(panel_side(bar, (408., 666.), area, edge), Rect { x, y, width: 408., height: 666. });
        }
        let tight = Rect { x: -500., y: -200., width: 500., height: 400. };
        assert_eq!(panel_side(bar, (600., 666.), tight, Edge::Bottom), tight);
    }
}
