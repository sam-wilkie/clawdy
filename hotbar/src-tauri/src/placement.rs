#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
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
