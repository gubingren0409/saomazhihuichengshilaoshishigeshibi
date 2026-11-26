from src.complete_geoapify_static import encode_polyline6
from src.verify_geoapify_views import fit_viewport


def test_polyline_encoding_preserves_lonlat_at_six_digits():
    assert encode_polyline6([[0.0, 0.0], [-0.000001, 0.000001]]) == "??A@"


def test_viewport_fit_accepts_same_scale_and_rejects_shift_or_image_change():
    view = {"extent_3857": [1000, 1000, 2200, 1900], "width": 1200, "height": 900}
    points = [(192, 144), (1008, 144), (192, 756), (1008, 756)]
    controls = [{"expected_px": [x, y], "observed_px": [x, y]} for x, y in points]
    fit = fit_viewport(view, controls, .99)
    assert fit["bounds_match"] and fit["extent_3857"] == view["extent_3857"]
    shifted = [{"expected_px": [x, y], "observed_px": [x+2, y]} for x, y in points]
    assert not fit_viewport(view, shifted, .99)["bounds_match"]
    assert fit_viewport(view, controls, .75)["actual_bounds"] is None
