from pathlib import Path

import joblib

from src.ml_training import FEATURES, train_models


def test_random_forest_training_is_reproducible(tmp_path: Path):
    dataset = Path(__file__).resolve().parents[1] / "src" / "ml_artifacts" / "dataset" / "tomato irrigation dataset.csv"
    results = train_models(dataset, tmp_path, algorithms=("rf",), crops=("tomato",))

    assert len(results) == 1
    assert results[0].f1 > 0.9
    artifact = tmp_path / results[0].artefacto
    assert artifact.is_file()

    model = joblib.load(artifact)
    assert list(model.feature_names_in_) == FEATURES
