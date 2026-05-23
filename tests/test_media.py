"""Tests for media file handling."""
from anki_git.formats.media import (
    MediaStrategy,
    handle_media,
    get_media_filenames_from_fields,
)


def test_media_strategy_values():
    assert MediaStrategy.NONE.value == "none"
    assert MediaStrategy.SYMLINK.value == "symlink"
    assert MediaStrategy.COPY.value == "copy"
    assert MediaStrategy.GIT_LFS.value == "git-lfs"


def test_get_filenames_from_sound_tag():
    fields = "Some text [sound:audio.mp3] more text"
    names = get_media_filenames_from_fields(fields)
    assert names == {"audio.mp3"}


def test_get_filenames_from_img_tag():
    fields = '<img src="image.jpg" alt="test">'
    names = get_media_filenames_from_fields(fields)
    assert names == {"image.jpg"}


def test_get_filenames_from_both():
    fields = '[sound:a.mp3] and <img src="b.jpg">'
    names = get_media_filenames_from_fields(fields)
    assert names == {"a.mp3", "b.jpg"}


def test_get_filenames_no_matches():
    fields = "plain text without media references"
    names = get_media_filenames_from_fields(fields)
    assert names == set()


def test_get_filenames_empty_string():
    names = get_media_filenames_from_fields("")
    assert names == set()


def test_get_filenames_with_paths():
    fields = '[sound:subdir/file.mp3] <img src="subdir/img.png">'
    names = get_media_filenames_from_fields(fields)
    assert names == {"subdir/file.mp3", "subdir/img.png"}


def test_get_filenames_duplicates():
    fields = '[sound:same.mp3] and [sound:same.mp3]'
    names = get_media_filenames_from_fields(fields)
    assert names == {"same.mp3"}


def test_handle_media_none_does_nothing(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    f = media_dir / "test.jpg"
    f.write_bytes(b"data")
    repo_media = tmp_path / "repo_media"
    handle_media(media_dir, repo_media, MediaStrategy.NONE, {"test.jpg"})
    assert not repo_media.exists()


def test_handle_media_copy(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    f = media_dir / "test.jpg"
    f.write_bytes(b"image data")
    repo_media = tmp_path / "repo_media"
    handle_media(media_dir, repo_media, MediaStrategy.COPY, {"test.jpg"})
    assert (repo_media / "test.jpg").exists()
    assert (repo_media / "test.jpg").read_bytes() == b"image data"


def test_handle_media_copy_multiple(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "a.jpg").write_bytes(b"a")
    (media_dir / "b.mp3").write_bytes(b"b")
    repo_media = tmp_path / "repo_media"
    handle_media(media_dir, repo_media, MediaStrategy.COPY, {"a.jpg", "b.mp3"})
    assert (repo_media / "a.jpg").read_bytes() == b"a"
    assert (repo_media / "b.mp3").read_bytes() == b"b"


def test_handle_media_copy_skips_nonexistent(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    repo_media = tmp_path / "repo_media"
    handle_media(media_dir, repo_media, MediaStrategy.COPY, {"missing.jpg"})
    assert repo_media.exists()
    assert not list(repo_media.iterdir())


def test_handle_media_copy_skips_existing(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "f.jpg").write_bytes(b"src")
    repo_media = tmp_path / "repo_media"
    repo_media.mkdir(parents=True)
    (repo_media / "f.jpg").write_bytes(b"existing")
    handle_media(media_dir, repo_media, MediaStrategy.COPY, {"f.jpg"})
    assert (repo_media / "f.jpg").read_bytes() == b"existing"


def test_handle_media_symlink(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    f = media_dir / "test.jpg"
    f.write_bytes(b"image data")
    repo_media = tmp_path / "repo_media"
    handle_media(media_dir, repo_media, MediaStrategy.SYMLINK, {"test.jpg"})
    link = repo_media / "test.jpg"
    assert link.exists()
    assert link.is_symlink()
    assert link.resolve() == f.resolve()


def test_handle_media_empty_filenames(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    repo_media = tmp_path / "repo_media"
    handle_media(media_dir, repo_media, MediaStrategy.COPY, set())
    assert repo_media.exists()
    assert not list(repo_media.iterdir())
