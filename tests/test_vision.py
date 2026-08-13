from datetime import datetime, timezone

import cv2
import numpy as np

from ow_automation.models import MatchResult, ScreenState
from ow_automation.capture import CapturedFrame, CaptureRegion
from ow_automation.vision import (
    KeywordClassifier,
    SceneClassifier,
    Template,
    TemplateMatcher,
    VisionPipeline,
)


def test_template_matcher_finds_template_and_location() -> None:
    frame = np.zeros((80, 100), dtype=np.uint8)
    template = np.array(
        [[0, 255, 0], [255, 255, 255], [0, 255, 0]], dtype=np.uint8
    )
    frame[20:23, 40:43] = template
    matcher = TemplateMatcher([Template("menu", template, threshold=0.99)], scales=(1.0,))

    detection = matcher.recognized(frame)[0]

    assert detection.label == "menu"
    assert detection.confidence > 0.99
    assert detection.bbox is not None
    assert detection.bbox.left == 40
    assert detection.bbox.top == 20


def test_template_matcher_supports_color_frames() -> None:
    frame = np.zeros((30, 30, 3), dtype=np.uint8)
    template = np.zeros((5, 5, 3), dtype=np.uint8)
    cv2.rectangle(template, (0, 0), (4, 4), (0, 255, 0), thickness=-1)
    template[2, 2] = (255, 255, 255)
    frame[8:13, 10:15] = template

    matcher = TemplateMatcher([Template("green", template, threshold=0.99)], scales=(1.0,))

    assert matcher.recognized(frame)[0].label == "green"


def test_template_matcher_uses_rgb_color_order_consistently() -> None:
    frame = np.zeros((30, 30, 3), dtype=np.uint8)
    template = np.zeros((5, 5, 3), dtype=np.uint8)
    template[:, :] = (255, 0, 0)
    template[2, 2] = (255, 255, 255)
    frame[8:13, 10:15] = template
    matcher = TemplateMatcher([Template("red", template, threshold=0.99)], scales=(1.0,))

    assert matcher.recognized(frame)[0].label == "red"


def test_keyword_classifier_identifies_result_in_english_and_chinese() -> None:
    classifier = KeywordClassifier({ScreenState.RESULT_CONFIRMED: ("match complete", "比赛结束")})

    english = classifier.classify("Match complete: Victory")
    chinese = classifier.classify("比赛结束：失败")

    assert english is not None
    assert english.state == ScreenState.RESULT_CONFIRMED
    assert english.result == MatchResult.VICTORY
    assert chinese is not None
    assert chinese.result == MatchResult.DEFEAT


def test_scene_classifier_returns_unknown_without_evidence() -> None:
    classifier = SceneClassifier({}, KeywordClassifier({}))

    observation = classifier.classify([])

    assert observation.state == ScreenState.UNKNOWN_SCREEN
    assert observation.confidence == 1.0


def test_vision_pipeline_adapts_captured_frame_to_runtime_classifier() -> None:
    template = np.zeros((5, 5), dtype=np.uint8)
    template[2, :] = 255
    template[:, 2] = 255
    image = np.zeros((20, 20), dtype=np.uint8)
    image[8:13, 10:15] = template
    frame = CapturedFrame(
        image=np.repeat(image[:, :, None], 3, axis=2),
        region=CaptureRegion(0, 0, 20, 20),
        captured_at=datetime.now(timezone.utc),
    )
    pipeline = VisionPipeline(
        TemplateMatcher([Template("main", template, threshold=0.99)], scales=(1.0,)),
        SceneClassifier({"main": ScreenState.MAIN_MENU}, KeywordClassifier({})),
    )

    observation = pipeline.classify(frame)

    assert observation.state == ScreenState.MAIN_MENU
    assert observation.confidence > 0.99
