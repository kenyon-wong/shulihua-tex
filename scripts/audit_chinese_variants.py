#!/usr/bin/env python3
"""Reject known traditional, Japanese-form, and obsolete variant regressions."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOK_ROOT = ROOT / "books"
TEX_ROOT = ROOT / "tex" / "books"
REPORT = ROOT / "reports" / "chinese-variant-audit.json"
BOOK_GLOB = "* - 数理化自学丛书编委会.md"
# OpenCC 0.1.7 t2s/tw2sp/hk2s unanimous mappings found in the 17-book corpus,
# plus four source-verified Japanese/obsolete forms: 鉄, 幷, 変, 搧.
DISALLOWED_CHARACTERS = frozenset(
    "們鋁濃鈉試結鋼說銅現鉀燒純較驗經構銀間絲論轉組氫紅紙檢蝕銹淨見識綫簡別鋅問連熱來細則織藍約釋鈣許証鏈軟漸飽續級計鍍烴須內鉛輕該磚沒黃綠紹題設鎂顏錳鑄廢鍵屬錫帶況詳鍋澤絕給時規維鏡強討縮揮緣蕩觀讀傳馬變銨纖單統彈負換損車預潤聞潑將參鉻順紡張狀過儲餾門針絨實繼謂滿頁編鎢發剛緩談貯腸韌應電為頂攪軌繞調傾場紀創溫滌淺鈴認剝暫詞圓縫銼裝錯鐳證篩鉍鎳釘納貴鉑據鋇備減殘輸瀝鉬鋪騰學決渾鮮烏閉話飯線鎘圍記遞脈動沖資費數軸脫徑個質繪顆亞誤這絳軍紗綜險無暢測閱鈷嗎魚熾脹濟閃輝覺鈍纜壺錠進鏽勻鉗闡氣墊蓋靜噴鈾導倫穩堅偉輪夾項領兩跡搖湯莖綸課輾鈹紋貧選擇劇併貼濘緊廂膩鈦錘釩闊揚閑側鑷鉤錄難濾輯員書龐慮貢邊鎮飲噁銻會讓魯撥貝鎚蛻糾庫晉驟軀鳥種賊鑒鳴飄濕爭尋終檸點鐵蘊於謹陣攝誰籠還確飴鐘挾薹蘿鱗燉駝鴨譯綾漁筆桿纏鉄幷変搧"
)
DISALLOWED_PHRASES = ("反覆",)


def scan_file(path: Path, findings: list[dict[str, object]]) -> None:
    relative = path.relative_to(ROOT).as_posix()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for column, character in enumerate(line, 1):
            if character in DISALLOWED_CHARACTERS:
                findings.append(
                    {
                        "book": relative,
                        "line": line_number,
                        "column": column,
                        "value": character,
                        "kind": "character",
                        "context": line[max(0, column - 21) : column + 20],
                    }
                )
        for phrase in DISALLOWED_PHRASES:
            start = 0
            while (index := line.find(phrase, start)) >= 0:
                findings.append(
                    {
                        "book": relative,
                        "line": line_number,
                        "column": index + 1,
                        "value": phrase,
                        "kind": "phrase",
                        "context": line[max(0, index - 20) : index + len(phrase) + 20],
                    }
                )
                start = index + len(phrase)


def main() -> int:
    findings: list[dict[str, object]] = []
    markdown_books = sorted(BOOK_ROOT.glob(BOOK_GLOB))
    tex_books = sorted(TEX_ROOT.glob("*.tex"))
    for book in markdown_books:
        scan_file(book, findings)
    for book in tex_books:
        scan_file(book, findings)
    report = {
        "schema_version": "1.0",
        "operation": "canonical-chinese-variant-audit",
        "status": "PASS" if len(markdown_books) == 17 and len(tex_books) == 17 and not findings else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "books": len(markdown_books),
        "tex_books": len(tex_books),
        "disallowed_character_types": len(DISALLOWED_CHARACTERS),
        "disallowed_phrases": list(DISALLOWED_PHRASES),
        "findings": findings,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "books": len(markdown_books),
                "tex_books": len(tex_books),
                "disallowed_character_types": len(DISALLOWED_CHARACTERS),
                "findings": len(findings),
                "status": report["status"],
            },
            ensure_ascii=False,
        )
    )
    if findings:
        for item in findings[:20]:
            print(
                f"ERROR: {item['book']}:{item['line']}:{item['column']}: "
                f"发现{item['kind']} {item['value']!r}: {item['context']}",
                file=sys.stderr,
            )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
