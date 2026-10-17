#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

pub fn resize_anchored(bar: Rect, size: (f64, f64), area: Rect) -> Rect {
    let (width, height) = (size.0.min(area.width), size.1.min(area.height));
    let near_left = bar.x - area.x <= area.x + area.width - bar.x - bar.width;
    let x = if near_left { bar.x } else { bar.x + bar.width - width };
    Rect { x: x.clamp(area.x, area.x + area.width - width),
        y: bar.y.clamp(area.y, area.y + area.height - height), width, height }
}

pub fn panel_side(bar: Rect, size: (f64, f64), area: Rect) -> Rect {
    let (width, height) = (size.0.min(area.width), size.1.min(area.height));
    let left = bar.x - width - 8.;
    let x = if left >= area.x { left } else { bar.x + bar.width + 8. };
    Rect { x: x.clamp(area.x, area.x + area.width - width),
        y: bar.y.clamp(area.y, area.y + area.height - height), width, height }
}

pub fn clamp(saved: Option<Rect>, size: (f64, f64), areas: &[Rect], primary: Rect) -> Rect {
    let area = saved.and_then(|r| areas.iter().find(|a| {
        let (cx, cy) = (r.x + r.width / 2., r.y + r.height / 2.);
        cx >= a.x && cx < a.x + a.width && cy >= a.y && cy < a.y + a.height
    })).copied();
    let a = area.unwrap_or(primary);
    let (width, height) = (size.0.min(a.width), size.1.min(a.height));
    let r = match (area, saved) {
        (Some(_), Some(r)) => r,
        _ => Rect { x: a.x + a.width - width - 8., y: a.y + (a.height - height) / 2., width, height },
    };
    Rect { x: r.x.clamp(a.x, a.x + a.width - width),
        y: r.y.clamp(a.y, a.y + a.height - height), width, height }
}

#[cfg(test)]
mod tests {
    use super::*;
    const PRIMARY: Rect = Rect { x: 0., y: 0., width: 1920., height: 1040. };
    const LEFT: Rect = Rect { x: -1280., y: -200., width: 1280., height: 1024. };
    const SIZE: (f64, f64) = (180., 300.);
    #[test]
    fn resizing_keeps_nearer_edge_and_clamps_including_negative_monitors() {
        assert_eq!(resize_anchored(bar(1732., 900.), (82., 140.), PRIMARY),
            Rect { x: 1830., y: 900., width: 82., height: 140. });
        assert_eq!(resize_anchored(bar(-1272., -190.), (82., 140.), LEFT),
            Rect { x: -1272., y: -190., width: 82., height: 140. });
        assert_eq!(resize_anchored(bar(1900., 1000.), (2000., 1200.), PRIMARY), PRIMARY);
    }
    #[test]
    fn panel_prefers_left_else_right_and_clamps_tight_areas() {
        assert_eq!(panel_side(bar(1700., 100.), (400., 650.), PRIMARY),
            Rect { x: 1292., y: 100., width: 400., height: 650. });
        assert_eq!(panel_side(bar(0., 900.), (400., 650.), PRIMARY),
            Rect { x: 188., y: 390., width: 400., height: 650. });
        let tight = Rect { x: -500., y: -200., width: 500., height: 400. };
        assert_eq!(panel_side(bar(-400., -150.), (400., 650.), tight),
            Rect { x: -400., y: -200., width: 400., height: 400. });
    }
    fn bar(x: f64, y: f64) -> Rect { Rect { x, y, width: SIZE.0, height: SIZE.1 } }

    #[test]
    fn missing_removed_and_fully_offscreen_use_primary_default() {
        for saved in [None, Some(bar(2500., 50.)), Some(bar(-3000., -900.))] {
            assert_eq!(clamp(saved, SIZE, &[PRIMARY], PRIMARY), bar(1732., 370.));
        }
        let offset = Rect { x: 100., y: -500., ..PRIMARY };
        assert_eq!(clamp(None, SIZE, &[offset], offset), bar(1832., -130.));
    }

    #[test]
    fn negative_monitor_and_partial_rects_are_clamped_by_their_centres() {
        let areas = [PRIMARY, LEFT];
        for (saved, expected) in [
            (bar(-1200., -100.), bar(-1200., -100.)),
            (bar(-1320., -250.), bar(-1280., -200.)),
            (bar(1800., 800.), bar(1740., 740.)),
            (bar(-50., -50.), bar(0., 0.)),
        ] {
            assert_eq!(clamp(Some(saved), SIZE, &areas, PRIMARY), expected);
        }
    }
}
