"""Each adapter's normalize() on small fixture files - no network."""

import json

import pytest
from stemsim.datasets.ccmsim import MAPPING, RATINGS, CCMSim
from stemsim.datasets.lastfm import LastFm, _cache_name
from stemsim.datasets.magnatagatune import COMPARISONS, MagnaTagATune
from stemsim.schema import PAIR, TRIPLET, song_track_id

MTAT_HEADER = (
    "clip1_id\tclip2_id\tclip3_id\tclip1_numvotes\tclip2_numvotes\tclip3_numvotes\t"
    "clip1_mp3_path\tclip2_mp3_path\tclip3_mp3_path\n"
)


def mtat_row(ids, votes):
    return "\t".join([*ids, *map(str, votes), *(f"0/{i}.mp3" for i in ids)]) + "\n"


def test_magnatagatune_sums_votes_across_orderings_and_skips_unclear_triples(registry):
    (registry.raw_dir("magnatagatune") / COMPARISONS).write_text(
        MTAT_HEADER
        + mtat_row(["a", "b", "c"], [3, 1, 6])
        + mtat_row(["b", "c", "a"], [0, 2, 1])  # same three clips, listed in another order
        + mtat_row(["d", "e", "f"], [2, 2, 0])  # tied for most votes - no clear outlier
        + mtat_row(["g", "h", "i"], [0, 0, 0]),  # nobody voted
        encoding="utf-8",
    )
    out = MagnaTagATune().normalize(registry)

    a, b, c = (f"mtat:0/{x}.mp3" for x in "abc")
    # c got 8 of 13 votes as the odd one out, so a and b are each other's closer match
    assert {(j.kind, j.a, j.b, j.c) for j in out.judgments} == {(TRIPLET, a, b, c), (TRIPLET, b, a, c)}
    assert all(j.value == pytest.approx(8 / 13) and j.weight == 13 for j in out.judgments)
    assert sorted(t.track_id for t in out.tracks) == [a, b, c]


def write_ccmsim(registry):
    raw = registry.raw_dir("ccmsim")
    (raw / MAPPING).write_text(
        "survey_audio_id,dataset,audio_file_path,survey_start_second,survey_end_second\n"
        "1_1,magnatagatune,0/x.mp3,4,24\n"
        "1_2,magnatagatune,0/y.mp3,4,24\n"
        "2_1,fma,030/030074.mp3,10,30\n"
        "3_1,carnatic,c.mp3,0,20\n",
        encoding="utf-8",
    )
    (raw / RATINGS).write_text(
        "audio_pair,overall_music_similarity,num_annotators\n1_1-1_2,0.5,2\n1_1-2_1,0.25,1\n1_1-3_1,0.9,1\n",
        encoding="utf-8",
    )


def test_ccmsim_keeps_western_pairs_and_shares_magnatagatune_tracks(registry):
    write_ccmsim(registry)
    out = CCMSim().normalize(registry)

    assert [(j.kind, j.a, j.b, j.value, j.weight) for j in out.judgments] == [
        (PAIR, "mtat:0/x.mp3", "mtat:0/y.mp3", 0.5, 2.0),
        (PAIR, "mtat:0/x.mp3", "fma:030/030074.mp3", 0.25, 1.0),
    ]
    # Same id as the MagnaTagATune adapter gives the clip, so audio is shared;
    # the excerpt the listeners heard is kept per membership
    clip = next(m for m in out.members if m.track_id == "mtat:0/x.mp3")
    assert (clip.clip_start, clip.clip_end) == (4.0, 24.0)


def test_ccmsim_all_cultures(registry):
    write_ccmsim(registry)
    assert len(CCMSim(cultures=None).normalize(registry).judgments) == 3


def test_lastfm_collapses_versions_and_skips_the_seed_itself(registry):
    seed = song_track_id("Karma Police", "Radiohead")
    similar = [
        {"name": "No Surprises", "artist": {"name": "Radiohead"}, "match": "0.8"},
        {"name": "No Surprises - Remastered 2009", "artist": {"name": "Radiohead"}, "match": "0.6"},
        {"name": "Karma Police - Live", "artist": {"name": "Radiohead"}, "match": "0.9"},  # a different recording
        {"name": "Karma Police - Remastered", "artist": {"name": "Radiohead"}, "match": "0.95"},  # the seed itself
        {"name": "Untitled", "artist": {}, "match": "0.5"},  # no artist - unusable
    ]
    raw = registry.raw_dir("lastfm")
    (raw / _cache_name(seed)).write_text(json.dumps({"seed": seed, "similar": similar}), encoding="utf-8")
    missing = song_track_id("Obscure", "Nobody")
    (raw / _cache_name(missing)).write_text(json.dumps({"seed": missing, "similar": []}), encoding="utf-8")

    out = LastFm().normalize(registry)

    pairs = {(j.b, j.value) for j in out.judgments}
    assert pairs == {
        (song_track_id("No Surprises", "Radiohead"), 0.8),
        (song_track_id("Karma Police - Live", "Radiohead"), 0.9),
    }
    assert all(j.kind == PAIR and j.a == seed and j.group == seed for j in out.judgments)
    assert missing not in {m.track_id for m in out.members}
