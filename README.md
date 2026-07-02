# Userhythm Key Splitter

Userhythm 채보 제작을 보조하기 위한 로컬 오디오 분석/키음 후보 분리 도구입니다.

목표는 곡을 자동으로 완성 채보로 바꾸는 것이 아니라, 로컬 음원에서 beat/onset/대역 에너지/악기성 후보를 뽑아 `.userhythm-analysis.json`으로 저장하고 Userhythm 에디터에서 제작자가 눈으로 보고 채택할 수 있게 만드는 것입니다.

## 왜 별도 레포인가

- Userhythm 본체의 플레이/에디터 안정성을 건드리지 않기 위해 분리합니다.
- Python, 딥러닝, FFmpeg, Demucs 같은 무거운 의존성을 웹 본체에 넣지 않습니다.
- 분석기는 로컬 제작 도구이고, 실제 플레이에는 필요하지 않습니다.
- 나중에 Electron 앱이나 별도 GUI로 키우기 쉽습니다.

## 현재 MVP 기능

- 로컬 mp3/wav/flac 파일 로드
- BPM/beat 후보 분석
- onset 후보 분석
- low/mid/high 주파수 대역 분류
- 8초 단위 section energy/density 요약
- Userhythm 에디터용 `.userhythm-analysis.json` 출력

## 설치

```powershell
cd C:\Users\user\Documents\coding\userhythm-key-splitter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

mp3 로드가 실패하면 FFmpeg가 필요할 수 있습니다.

## 사용

```powershell
userhythm-key-splitter analyze "C:\path\song.mp3"
```

출력 파일:

```text
song.userhythm-analysis.json
```

옵션 예:

```powershell
userhythm-key-splitter analyze "song.mp3" --bpm 126 --offset-ms -235 --sensitivity 0.7 --min-gap-ms 60
userhythm-key-splitter analyze "song.wav" --mode detailed --output "song.userhythm-analysis.json"
```

## Userhythm 에디터와 연동

1. 이 도구로 `.userhythm-analysis.json`을 생성합니다.
2. Userhythm 채보 에디터에서 `분석 불러오기`를 누릅니다.
3. 분석 JSON을 선택합니다.
4. 타임라인에 beat/onset 마커가 표시됩니다.

## 출력 형식

```json
{
  "metadata": {},
  "timing": {},
  "beats": [],
  "onsets": [],
  "bands": [],
  "sections": []
}
```

## 향후 방향

- Demucs 기반 stem 분리: drums/bass/vocals/other
- stem별 onset 생성
- lane hint 추천
- ghost note 후보 생성
- 기존 채보와 onset mismatch 검사
- Userhythm Electron Player/Editor와 직접 연동

## 원칙

- 분석 결과는 채보 원본을 직접 바꾸지 않습니다.
- 자동 생성 노트는 항상 후보/ghost로만 취급합니다.
- 로컬 음원과 YouTube 음원이 다를 수 있으므로 offset 조정을 전제로 합니다.
