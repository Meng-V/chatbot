"""
Unit tests for the ETL metadata classifier.

Run: `python -m scripts.etl.test_classify` from ai-core/.

Every chunk inherits the document's classified metadata. Wrong tags
here cascade into every downstream layer:

  - wrong campus  -> chunk excluded by scope filter at retrieval, OR
                    surfaced for the wrong campus's questions
  - wrong library -> chunk surfaced for "King hours" when it should
                    have been Wertz
  - wrong featured_service -> retrieval boost fires on wrong intent;
                              UrlSeen.priority gets miscategorized

Tests pin every config-table-driven decision so a future PR adding a
new sitemap path can verify it routes correctly before hitting prod.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from ai-core/ as `python -m scripts.etl.test_classify`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from scripts.etl.classify import DocMetadata, classify  # noqa: E402


# --- Campus inference (URL host) ----------------------------------------


def test_oxford_host_resolves_to_oxford() -> None:
    out = classify("https://www.lib.miamioh.edu/use/borrow/ill/", "body text")
    assert out.campus == "oxford"


def test_hamilton_host_resolves_to_hamilton() -> None:
    out = classify("https://www.ham.miamioh.edu/library/services/", "body")
    assert out.campus == "hamilton"


def test_middletown_host_resolves_to_middletown() -> None:
    out = classify("https://mid.miamioh.edu/library/about/", "body")
    assert out.campus == "middletown"


def test_unknown_host_falls_back_to_oxford() -> None:
    """Conservative default: a NON-seed LibGuide URL we forgot to tag
    falls into Oxford rather than crashing or being campus-less. (The
    registry override only applies to LIBGUIDE_SEED URLs, so this
    stays valid.)"""
    out = classify("https://libguides.lib.miamioh.edu/research/", "body")
    assert out.campus == "oxford"


# --- Curated LibGuide registry override (the cross-campus landmine) ---


def test_libguide_tec_lab_is_middletown_not_host_default_oxford() -> None:
    """LOAD-BEARING: the Middletown TEC Lab guide MUST tag
    campus=middletown. Host inference would default it to 'oxford',
    and the cross-campus guard would then BLOCK it for Middletown
    queries (the exact reason fs_makerspace_middletown_refusal could
    not be answered)."""
    out = classify(
        "https://libguides.lib.miamioh.edu/middletown_tec_lab/home", ""
    )
    assert out.campus == "middletown"
    assert out.library == "gardner_harvey"
    assert out.featured_service == "makerspace"


def test_libguide_citation_is_university_wide() -> None:
    out = classify("https://libguides.lib.miamioh.edu/citation", "")
    assert out.campus == "all"
    assert out.library == "all"
    assert out.featured_service is None


def test_libguide_create_makerspace_is_oxford_king() -> None:
    out = classify(
        "https://libguides.lib.miamioh.edu/create/makerspace", ""
    )
    assert out.campus == "oxford"
    assert out.library == "king"
    assert out.featured_service == "makerspace"


def test_libguide_newspapers_featured_service() -> None:
    out = classify("https://libguides.lib.miamioh.edu/newspapers", "")
    assert out.campus == "all"
    assert out.featured_service == "newspapers"


# --- Library inference (URL substring) ---------------------------------


def test_king_library_url_resolves_to_king() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/about/locations/king-library/",
        "body",
    )
    assert out.library == "king"


def test_wertz_url_resolves_to_wertz() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/about/locations/art-arch/",
        "body",
    )
    assert out.library == "wertz"


def test_special_collections_url_resolves_to_special() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/about/locations/special-collections-archives/",
        "body",
    )
    assert out.library == "special"


def test_hamilton_host_implies_rentschler() -> None:
    """Regional default: any ham.miamioh.edu URL defaults to Rentschler."""
    out = classify("https://www.ham.miamioh.edu/library/about/", "body")
    assert out.library == "rentschler"


def test_middletown_host_implies_gardner_harvey() -> None:
    out = classify("https://www.mid.miamioh.edu/library/", "body")
    assert out.library == "gardner_harvey"


def test_sword_path_overrides_to_sword() -> None:
    """SWORD is on the Middletown campus but not the Gardner-Harvey
    library. The /sword/ path substring overrides the host-default."""
    out = classify("https://www.mid.miamioh.edu/sword/about/", "body")
    assert out.library == "sword"


def test_no_library_substring_returns_none() -> None:
    """A generic /use/borrow/ill/ URL has no specific library; library
    stays None and retrieval surfaces by ranking."""
    out = classify("https://www.lib.miamioh.edu/use/borrow/ill/", "body")
    assert out.library is None
    # Campus still set.
    assert out.campus == "oxford"


def test_body_text_not_used_for_library() -> None:
    """A King page that mentions 'Hamilton' in passing must NOT be
    re-tagged as Hamilton. Plan §8 hard rule."""
    body = (
        "King Library hosts a special exhibit about Alexander Hamilton."
    )
    out = classify(
        "https://www.lib.miamioh.edu/about/locations/king-library/",
        body,
    )
    assert out.library == "king"
    assert out.campus == "oxford"  # body shouldn't shift this either


# --- Topic inference (URL prefix) ---------------------------------------


def test_use_borrow_resolves_to_borrow_topic() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/borrow/ill/",
        "body",
    )
    assert out.topic == "borrow"


def test_use_spaces_resolves_to_spaces() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/spaces/makerspace/",
        "body",
    )
    assert out.topic == "spaces"


def test_use_technology_resolves_to_technology() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/technology/printing/",
        "body",
    )
    assert out.topic == "technology"


def test_research_resolves_to_research() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/research/find/databases/",
        "body",
    )
    assert out.topic == "research"


def test_about_locations_resolves_to_about() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/about/locations/king-library/",
        "body",
    )
    assert out.topic == "about"


def test_digital_collections_resolves_to_collections() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/digital-collections/walter-havighurst/",
        "body",
    )
    assert out.topic == "collections"


def test_use_without_subpath_resolves_to_service() -> None:
    """Lone `/use/` (no /borrow/spaces/technology suffix) falls into
    the catch-all 'service' bucket -- not the more-specific siblings."""
    out = classify(
        "https://www.lib.miamioh.edu/use/services/faculty/",
        "body",
    )
    assert out.topic == "service"


def test_unknown_path_defaults_to_about() -> None:
    """Safe default: unknown paths get 'about' tag rather than
    crashing or empty-string tag."""
    out = classify(
        "https://www.lib.miamioh.edu/totally-new-section/page/",
        "body",
    )
    assert out.topic == "about"


# --- Featured-service inference ----------------------------------------


def test_adobe_software_url_tagged_adobe() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/technology/software/adobe-creative-cloud/",
        "body",
    )
    assert out.featured_service == "adobe_checkout"


def test_ill_url_tagged_ill() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/borrow/ill/",
        "body",
    )
    assert out.featured_service == "ill"


def test_makerspace_url_tagged_makerspace() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/spaces/makerspace/",
        "body",
    )
    assert out.featured_service == "makerspace"


def test_digital_collections_url_tagged_digital_collections() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/digital-collections/oxford-history/",
        "body",
    )
    assert out.featured_service == "digital_collections"


def test_special_collections_url_tagged_special_collections() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/about/locations/special-collections-archives/",
        "body",
    )
    assert out.featured_service == "special_collections"


def test_non_featured_url_has_no_featured_tag() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/about/organization/contact-us/",
        "body",
    )
    assert out.featured_service is None


# --- Audience inference (URL path-driven, conservative) ----------------


def test_student_url_tagged_student() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/services/students/",
        "body",
    )
    assert "student" in out.audience


def test_faculty_url_tagged_faculty() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/services/faculty/",
        "body",
    )
    assert "faculty" in out.audience


def test_grad_url_tagged_grad() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/services/graduate/students/",
        "body",
    )
    assert "grad" in out.audience


def test_new_student_url_tagged_new_student() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/services/new-students/",
        "body",
    )
    assert "new_student" in out.audience


def test_no_audience_signal_returns_all() -> None:
    """Conservative default: a generic page is for everyone. Don't
    over-tag and shrink retrieval coverage."""
    out = classify(
        "https://www.lib.miamioh.edu/use/borrow/ill/",
        "body",
    )
    assert out.audience == ["all"]


def test_multi_audience_url_returns_sorted() -> None:
    """Determinism: if multiple audiences match, output is sorted so
    snapshot logs don't flap."""
    out = classify(
        "https://www.lib.miamioh.edu/use/services/faculty/staff/students/",
        "body",
    )
    # Both faculty and student matched. Sorted order: ['faculty', 'student'].
    assert out.audience == sorted(out.audience)
    assert "faculty" in out.audience and "student" in out.audience


# --- DocMetadata shape + immutability -----------------------------------


def test_classify_returns_DocMetadata() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/use/spaces/makerspace/",
        "body",
    )
    assert isinstance(out, DocMetadata)
    # Frozen: mutation rejected.
    try:
        out.campus = "hamilton"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("expected frozen dataclass to refuse mutation")


# --- End-to-end shape checks for marquee URLs --------------------------


def test_makerspace_full_classification() -> None:
    """The MakerSpace page is the highest-traffic featured-service URL.
    Every tag must be right."""
    out = classify(
        "https://www.lib.miamioh.edu/use/spaces/makerspace/",
        "MakerSpace at King Library hosts 3D printers...",
    )
    assert out.campus == "oxford"
    assert out.topic == "spaces"
    assert out.featured_service == "makerspace"
    # Library is None for /use/spaces/makerspace/ (no /about/locations/ in URL).
    # The synthesizer joins via LibrarySpace.libcal_id -> king.
    assert out.library is None


def test_rentschler_about_page_full_classification() -> None:
    """Hamilton-campus URLs default to Rentschler library."""
    out = classify(
        "https://www.ham.miamioh.edu/library/about/hours/",
        "body",
    )
    assert out.campus == "hamilton"
    assert out.library == "rentschler"


def test_special_collections_full_classification() -> None:
    out = classify(
        "https://www.lib.miamioh.edu/about/locations/special-collections-archives/",
        "body",
    )
    assert out.campus == "oxford"
    assert out.library == "special"
    assert out.topic == "about"
    assert out.featured_service == "special_collections"


def main() -> int:
    tests = [
        test_oxford_host_resolves_to_oxford,
        test_hamilton_host_resolves_to_hamilton,
        test_middletown_host_resolves_to_middletown,
        test_unknown_host_falls_back_to_oxford,
        test_king_library_url_resolves_to_king,
        test_wertz_url_resolves_to_wertz,
        test_special_collections_url_resolves_to_special,
        test_hamilton_host_implies_rentschler,
        test_middletown_host_implies_gardner_harvey,
        test_sword_path_overrides_to_sword,
        test_no_library_substring_returns_none,
        test_body_text_not_used_for_library,
        test_use_borrow_resolves_to_borrow_topic,
        test_use_spaces_resolves_to_spaces,
        test_use_technology_resolves_to_technology,
        test_research_resolves_to_research,
        test_about_locations_resolves_to_about,
        test_digital_collections_resolves_to_collections,
        test_use_without_subpath_resolves_to_service,
        test_unknown_path_defaults_to_about,
        test_adobe_software_url_tagged_adobe,
        test_ill_url_tagged_ill,
        test_makerspace_url_tagged_makerspace,
        test_digital_collections_url_tagged_digital_collections,
        test_special_collections_url_tagged_special_collections,
        test_non_featured_url_has_no_featured_tag,
        test_student_url_tagged_student,
        test_faculty_url_tagged_faculty,
        test_grad_url_tagged_grad,
        test_new_student_url_tagged_new_student,
        test_no_audience_signal_returns_all,
        test_multi_audience_url_returns_sorted,
        test_classify_returns_DocMetadata,
        test_makerspace_full_classification,
        test_rentschler_about_page_full_classification,
        test_special_collections_full_classification,
        test_libguide_tec_lab_is_middletown_not_host_default_oxford,
        test_libguide_citation_is_university_wide,
        test_libguide_create_makerspace_is_oxford_king,
        test_libguide_newspapers_featured_service,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
