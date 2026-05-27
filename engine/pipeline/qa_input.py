from __future__ import annotations

import json
import re
from typing import Optional


def append_packet_block(lines: list[str], packet: Optional[dict]) -> None:
    if not packet:
        return
    pkt = json.dumps(packet, ensure_ascii=False, indent=0)[:4000]
    lines.extend(["", "[리서치 패킷]", pkt, ""])
