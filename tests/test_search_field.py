from image_classifier.ui.search_field import fold, matches


def test_accents_and_case_are_ignored():
    assert fold("Navegación") == "navegacion"
    assert matches("NAVEGACION", "Fin", "Navegación al final")


def test_infinitive_finds_the_command_form():
    assert matches("guardar", "Ctrl+S", "Guarda las modificaciones en la imagen actual")
    assert matches("eliminar", "Supr", "Elimina la imagen actual")
    assert not matches("guardar", "F", "Marcar o desmarcar imagen como Favorita")


def test_single_character_matches_only_the_key_and_empty_matches_all():
    assert matches("f", "F", "Toggle Favorite")
    assert not matches("f", "Shift+F", "Toggle Favorite filter")
    assert matches("", "x", "y")


def test_every_word_must_match():
    assert matches("guarda imagen", "Ctrl+S", "Guarda las modificaciones en la imagen actual")
    assert not matches("guarda zoom", "Ctrl+S", "Guarda las modificaciones en la imagen actual")
