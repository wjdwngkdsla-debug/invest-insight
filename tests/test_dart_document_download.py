from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.sources import dart_api


class _Response:
    def __init__(self, text: str, content: bytes | None = None) -> None:
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")

    def raise_for_status(self) -> None:
        return None


class DartDocumentDownloadTest(unittest.TestCase):
    def test_viewer_root_nodes_extracts_top_level_document_parts(self) -> None:
        html = """
        <script>
          var node1 = {};
          node1['dcmNo'] = "11558757";
          node1['eleId'] = "6";
          node1['offset'] = "93134";
          node1['length'] = "1748497";
          node1['dtd'] = "dart4.xsd";
          treeData.push(node1);
        </script>
        """

        self.assertEqual(dart_api._viewer_root_nodes(html), [{
            "dcmNo": "11558757", "eleId": "6", "offset": "93134",
            "length": "1748497", "dtd": "dart4.xsd",
        }])

    def test_public_viewer_is_used_when_document_api_returns_error_xml(self) -> None:
        error = "<result><status>020</status><message>요청 제한</message></result>"
        index = """
        var node1 = {};
        node1['dcmNo'] = "123";
        node1['eleId'] = "1";
        node1['offset'] = "10";
        node1['length'] = "20";
        node1['dtd'] = "dart4.xsd";
        treeData.push(node1);
        """
        viewer = "<TABLE><TR><TD>희망공모가액 9,400원~11,500원</TD></TR></TABLE>"

        with (
            patch.object(dart_api, "DART_API_KEY", "test-key"),
            patch.object(
                dart_api.requests,
                "get",
                side_effect=[_Response(error), _Response(index), _Response(viewer)],
            ) as get,
        ):
            result = dart_api.download_document_text("20260828001853")

        self.assertEqual(result, viewer)
        self.assertEqual(get.call_count, 3)

    def test_public_viewer_is_used_when_document_api_request_fails(self) -> None:
        index = """
        var node1 = {};
        node1['dcmNo'] = "123";
        node1['eleId'] = "1";
        node1['offset'] = "10";
        node1['length'] = "20";
        node1['dtd'] = "dart4.xsd";
        treeData.push(node1);
        """
        viewer = "<TABLE><TR><TD>청약기일 2026년 10월 6일</TD></TR></TABLE>"

        with (
            patch.object(dart_api, "DART_API_KEY", "test-key"),
            patch.object(
                dart_api.requests,
                "get",
                side_effect=[dart_api.requests.ConnectionError("timeout"), _Response(index), _Response(viewer)],
            ),
        ):
            result = dart_api.download_document_text("20260828001853")

        self.assertEqual(result, viewer)


if __name__ == "__main__":
    unittest.main()
