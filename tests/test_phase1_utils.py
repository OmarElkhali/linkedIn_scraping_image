from core.alumni_osint_pipeline import make_high_res_image_url, normalize_name_for_filename


def test_high_res_hack_shrink():
    source = "https://media.licdn.com/dms/image/v2/abc/profile-displayphoto-shrink_100_100/profile-displayphoto-shrink_100_100/0/xyz"
    out = make_high_res_image_url(source, 800)
    assert "shrink_800_800" in out
    assert "shrink_100_100" not in out


def test_high_res_hack_scale():
    source = "https://media.licdn.com/dms/image/v2/abc/profile-displayphoto-scale_100_100/B4/0/xyz"
    out = make_high_res_image_url(source, 1200)
    assert "scale_1200_1200" in out


def test_filename_normalization():
    assert normalize_name_for_filename("Fatima Zahra El Magana") == "Fatima_Zahra_El_Magana"
    assert normalize_name_for_filename("  éèà  ") == "eea"
    assert normalize_name_for_filename("") == "unknown_profile"
