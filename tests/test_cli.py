import json

import pytest

from conftest import EXAMPLES, row
from laser_jig import cli
from laser_jig.cli import read_rows, row_problems

HEADER = "product,folder,blank_w_mm,blank_h_mm,blank_z_mm,shape,layout,pocket_type,tolerance,tab_w_mm,tab_l_mm\n"


def write_csv(path, *lines, header=HEADER):
    path.write_text(header + "".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def outputs(folder):
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def test_example_csv_generates_every_file(tmp_path, capsys):
    assert cli.main(["generate", str(EXAMPLES / "blanks.csv"), "-o", str(tmp_path)]) == 0
    made = outputs(tmp_path)
    assert len(made) == 2 * len(read_rows(EXAMPLES / "blanks.csv"))
    assert "coasters/round_coaster_jig.stl" in made and "coasters/round_coaster_jig.svg" in made


def test_existing_outputs_are_never_replaced_without_overwrite(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "b.csv", "tile,,40,30,3,rect,1x1,4wall,tight,,")
    out = tmp_path / "out"
    assert cli.main(["generate", str(csv_path), "-o", str(out), "--only", "svg"]) == 0
    target = out / "tile_jig.svg"
    target.write_text("keep me", encoding="utf-8")
    capsys.readouterr()
    assert cli.main(["generate", str(csv_path), "-o", str(out)]) == 2
    assert "already exist" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == "keep me"
    assert not (out / "tile_jig.stl").exists(), "nothing may be written when any output already exists"
    assert cli.main(["generate", str(csv_path), "-o", str(out), "--overwrite"]) == 0
    assert target.read_text(encoding="utf-8").startswith("<?xml")


def test_only_stl(tmp_path):
    csv_path = write_csv(tmp_path / "b.csv", "tile,,40,30,3,rect,1x1,4wall,tight,,")
    assert cli.main(["generate", str(csv_path), "-o", str(tmp_path / "o"), "--only", "stl", "-q"]) == 0
    assert outputs(tmp_path / "o") == ["tile_jig.stl"]


def test_every_bad_row_is_listed_and_nothing_is_written(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "b.csv",
                         "good,,40,30,3,rect,1x1,4wall,tight,,",
                         "wide,,200,30,3,rect,1x1,4wall,tight,,",
                         "oops,,abc,30,3,star,1x1,4wall,snug,,",
                         "../escape,,40,30,3,rect,1x1,4wall,tight,,")
    out = tmp_path / "out"
    assert cli.main(["generate", str(csv_path), "-o", str(out)]) == 2
    err = capsys.readouterr().err
    assert "3 row(s)" in err
    for fragment in ("line 3 (wide)", "207.0 mm across", "line 4 (oops)", "'abc' is not a number", "shape 'star'",
                     "tolerance must be", "line 5", "becomes the file name"):
        assert fragment in err
    assert "line 2" not in err
    assert not out.exists()


@pytest.mark.parametrize("overrides, fragment", [
    ({"product": ""}, "product must be"),
    ({"product": "a/b"}, "product must be"),
    ({"product": "..\\b"}, "product must be"),
    ({"folder": "x/y"}, "folder must be"),
    ({"folder": ".."}, "folder must be"),
    ({"blank_w_mm": "0"}, "greater than 0"),
    ({"blank_w_mm": "nan"}, "finite"),
    ({"blank_h_mm": ""}, "blank_h_mm is empty"),
    ({"blank_z_mm": "-1"}, "greater than 0"),
    ({"tab_w_mm": "-2"}, "can't be negative"),
    ({"layout": "2by1"}, "layout"),
    ({"layout": "0x1"}, "layout"),
    ({"pocket_type": "cylinder"}, "doesn't go with shape rect"),
    ({"shape": "circle", "pocket_type": "cylinder", "layout": "2x1"}, "layout must be 1x1"),
    ({"shape": "tombstone", "pocket_type": "tombstone_pocket", "blank_h_mm": "10"}, "taller than half"),
    ({"blank_w_mm": "100", "layout": "2x1"}, "mm across"),
    ({"blank_h_mm": "104"}, "front to back"),
    ({"blank_z_mm": "8"}, None),
    ({"shape": "rect", "pocket_type": "3wall", "blank_w_mm": "120", "blank_h_mm": "10"}, "front to back"),
])
def test_row_problems(overrides, fragment):
    problems = row_problems(row(**overrides))
    if fragment is None:
        assert problems == []
    else:
        assert any(fragment in p for p in problems), problems


def test_designs_that_overrun_the_plate_on_purpose_are_allowed():
    assert row_problems(row(blank_h_mm="140", pocket_type="3wall_overrun")) == []
    assert row_problems(row(shape="tombstone", pocket_type="tombstone_pocket", blank_w_mm="50",
                            blank_h_mm="130")) == []


def test_plate_size_options_change_what_fits(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "b.csv", "big,,180,30,3,rect,1x1,4wall,tight,,")
    assert cli.main(["generate", str(csv_path), "-o", str(tmp_path / "a")]) == 2
    assert cli.main(["generate", str(csv_path), "-o", str(tmp_path / "b"), "--width", "200", "-q"]) == 0


def test_thin_plate_rejects_thick_blanks(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "b.csv", "tile,,40,30,3,rect,1x1,4wall,tight,,")
    assert cli.main(["generate", str(csv_path), "-o", str(tmp_path / "o"), "--thickness", "4"]) == 2
    assert "deeper than the 4 mm plate" in capsys.readouterr().err


def test_bad_plate_option(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "b.csv", "tile,,40,30,3,rect,1x1,4wall,tight,,")
    assert cli.main(["generate", str(csv_path), "--width", "0"]) == 2
    assert "width must be" in capsys.readouterr().err


@pytest.mark.parametrize("header, fragment", [
    ("product,blank_w_mm\n", "missing column(s)"),
    (HEADER.strip() + ",colour\n", "unknown column(s): colour"),
])
def test_csv_header_problems(tmp_path, capsys, header, fragment):
    csv_path = write_csv(tmp_path / "b.csv", header=header)
    assert cli.main(["generate", str(csv_path), "-o", str(tmp_path / "o")]) == 2
    assert fragment in capsys.readouterr().err


def test_duplicate_products_are_rejected(tmp_path):
    csv_path = write_csv(tmp_path / "b.csv", "tile,,40,30,3,rect,1x1,4wall,tight,,",
                         "TILE,,30,30,3,rect,1x1,4wall,tight,,")
    with pytest.raises(ValueError, match="same product and folder as line 2"):
        read_rows(csv_path)


def test_extra_values_and_empty_files(tmp_path):
    with pytest.raises(ValueError, match="more values than columns"):
        read_rows(write_csv(tmp_path / "a.csv", "tile,,40,30,3,rect,1x1,4wall,tight,,,extra"))
    with pytest.raises(ValueError, match="has no rows"):
        read_rows(write_csv(tmp_path / "b.csv", ",,,,,,,,,,"))
    with pytest.raises(ValueError, match="couldn't read"):
        read_rows(tmp_path / "missing.csv")


def test_spreadsheet_csv_with_bom_and_spaces(tmp_path):
    p = tmp_path / "excel.csv"
    p.write_bytes(("\ufeff" + HEADER + " tile , ,40 ,30,3, rect,1X1,4wall,tight,,\n").encode("utf-8"))
    (r,) = read_rows(p)
    assert (r["product"], r["shape"], r["layout"]) == ("tile", "rect", "1x1")


def test_doctor_is_safe_to_paste(capsys):
    assert cli.main(["doctor", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["cad_kernel"] == "ok"
    assert set(report["packages"]) >= {"build123d", "numpy"}


def test_doctor_redacts_home_and_email():
    from laser_jig.doctor import redact
    text = redact("/Users/someone/x C:\\Users\\other\\y a@b.example token=abc")
    assert "someone" not in text and "other" not in text and "a@b.example" not in text and "abc" not in text


# ── Review fixes ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("overrides, fragment", [
    ({"shape": "wallet", "pocket_type": "wallet_pocket", "blank_w_mm": "8", "blank_h_mm": "30"}, "at least 10"),
    ({"shape": "wallet", "pocket_type": "wallet_pocket", "blank_w_mm": "30", "blank_h_mm": "6"}, "at least 10"),
    ({"shape": "tombstone", "pocket_type": "tombstone_pocket", "blank_w_mm": "4", "blank_h_mm": "30"}, "at least 10"),
    ({"tab_w_mm": "45", "tab_l_mm": "5"}, "tab_w_mm"),
    ({"tab_w_mm": "5", "tab_l_mm": "500"}, "tab_l_mm"),
    ({"pocket_type": "3wall", "blank_w_mm": "50", "blank_h_mm": "15", "tab_w_mm": "20"}, "tab_w_mm"),
    ({"pocket_type": "3wall_overrun", "blank_h_mm": "5000"}, "blank_h_mm"),
    ({"blank_w_mm": "5000"}, "blank_w_mm"),
    ({"blank_z_mm": "900"}, "blank_z_mm"),
    ({"layout": "1x2", "blank_h_mm": "20", "tab_w_mm": "5", "tab_l_mm": "5"}, "ring slots"),
    ({"pocket_type": "3wall", "layout": "1x2", "blank_w_mm": "30", "blank_h_mm": "10", "tab_w_mm": "4"}, "ring slots"),
    ({"pocket_type": "3wall_top_notch", "layout": "1x2", "blank_w_mm": "30", "blank_h_mm": "10", "tab_w_mm": "4"},
     "ring slots"),
    ({"shape": "heart", "pocket_type": "heart_profile", "layout": "1x2", "blank_w_mm": "30", "blank_h_mm": "28",
      "tab_w_mm": "4", "tab_l_mm": "4"}, "ring slots"),
    ({"product": "con"}, "reserved"),
    ({"product": "LPT9"}, "reserved"),
    ({"folder": "Nul"}, "reserved"),
    ({"folder": "com1"}, "reserved"),
])
def test_rows_that_would_crash_or_damage_the_jig_are_rejected(overrides, fragment):
    problems = row_problems(row(**overrides))
    assert any(fragment in p for p in problems), problems


def test_multi_row_without_slots_and_ring_slot_in_single_row_are_fine():
    assert row_problems(row(layout="1x2", blank_h_mm="20")) == []
    assert row_problems(row(pocket_type="3wall", layout="3x1", blank_w_mm="50", blank_h_mm="15", tab_w_mm="6")) == []


def test_smallest_valid_wallet_and_tombstone_build(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "b.csv", "w,,10,10,2,wallet,1x1,wallet_pocket,tight,,",
                         "t,,10,30,2,tombstone,1x1,tombstone_pocket,tight,,")
    assert cli.main(["generate", str(csv_path), "-o", str(tmp_path / "o"), "-q"]) == 0


def test_a_geometry_failure_is_a_clean_error_and_writes_nothing(tmp_path, capsys, monkeypatch):
    import laser_jig.stl as stl

    def boom(row):
        if row["product"] == "second":
            raise RuntimeError("kernel failure")
        return real(row)
    real = stl.build_jig
    monkeypatch.setattr(stl, "build_jig", boom)
    csv_path = write_csv(tmp_path / "b.csv", "first,,40,30,3,rect,1x1,4wall,tight,,",
                         "second,,40,30,3,rect,1x1,4wall,tight,,")
    out = tmp_path / "o"
    assert cli.main(["generate", str(csv_path), "-o", str(out)]) == 1
    err = capsys.readouterr().err
    assert "line 3 (second)" in err and "kernel failure" in err and "Traceback" not in err
    assert not out.exists() or outputs(out) == []


def test_out_dir_that_is_a_file(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "b.csv", "tile,,40,30,3,rect,1x1,4wall,tight,,")
    blocker = tmp_path / "taken"
    blocker.write_text("x", encoding="utf-8")
    assert cli.main(["generate", str(csv_path), "-o", str(blocker)]) == 2
    assert "not a folder" in capsys.readouterr().err
    assert blocker.read_text(encoding="utf-8") == "x"


def test_write_errors_are_clean(tmp_path, capsys, monkeypatch):
    import laser_jig.cli as c
    csv_path = write_csv(tmp_path / "b.csv", "tile,,40,30,3,rect,1x1,4wall,tight,,")

    def denied(*a, **k):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(c.os, "replace", denied)
    assert cli.main(["generate", str(csv_path), "-o", str(tmp_path / "o")]) == 1
    err = capsys.readouterr().err
    assert "Permission denied" in err and "Traceback" not in err
    assert not list((tmp_path / "o").rglob("*.part")), "temporary files must be cleaned up"


def test_outputs_are_written_atomically(tmp_path, monkeypatch):
    import laser_jig.cli as c
    seen = []
    real = c.os.replace

    def spy(src, dst):
        seen.append((str(src), str(dst)))
        return real(src, dst)
    monkeypatch.setattr(c.os, "replace", spy)
    csv_path = write_csv(tmp_path / "b.csv", "tile,,40,30,3,rect,1x1,4wall,tight,,")
    assert cli.main(["generate", str(csv_path), "-o", str(tmp_path / "o"), "-q"]) == 0
    assert sorted(d.rsplit(".", 1)[1] for _, d in seen) == ["stl", "svg"]
    assert all(s == d + ".part" for s, d in seen)


def test_svg_uses_unix_line_endings(tmp_path):
    from laser_jig.svg import generate_svg
    data = open(generate_svg(row(), str(tmp_path)), "rb").read()
    assert b"\r" not in data and data.startswith(b"<?xml")
