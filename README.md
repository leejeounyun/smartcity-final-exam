# 스마트시티 기말과제

판교 제1테크노밸리와 청라 국제업무지구를 비교하여, 업무지구의 성공과 부진 원인을 데이터 기반으로 분석하는 프로젝트다.

## 비교 대상

- 기준 지역: 판교 제1테크노밸리
- 비교 지역: 청라 국제업무지구

## 저장소 구성

```text
data/
  raw/
  processed/
docs/
scripts/
web/
index.html
```

## 현재 포함된 원천 데이터

- 경계 GeoJSON
  - `data/raw/pangyo_boundary.geojson`
  - `data/raw/cheongna_boundary.geojson`
- 지하철 네트워크
  - `data/raw/subway_network/`
- 토지이용계획공간정보
  - `data/raw/AL_D154_41_20260412/`
  - `data/raw/AL_D154_28_20260412/`
- 건축물 공간정보 및 표제부
  - `data/raw/building/`
- SGIS 집계구 경계 및 인구/종사자
  - `data/raw/sgis/`

## 전처리 실행

다음 명령으로 비교분석용 데이터를 생성한다.

```bash
python scripts/build_final_exam_base_datasets.py
```

## 전처리 산출물

전처리 결과는 `data/processed/` 아래에 생성된다.

- 지역 경계
- 토지이용 GeoJSON
- 건축물 GeoJSON
- 집계구 인구/종사자 GeoJSON
- 30/60분 등시시간권 GeoJSON
- 도달 가능 역 GeoJSON
- 요약 지표 `summary.json`

## 웹 시스템

- 진입 파일: `index.html`
- 실제 앱: `web/index.html`

웹 시스템은 다음 기능을 포함한다.

- 지역 전환
- 토지이용/건축물, 교통 접근성, 인구·종사자 레이어 전환
- 30분/60분 등시시간권 전환
- 판교 vs 청라 핵심 지표 비교
- 누적 접근성 곡선 시각화

## 경계 정의

경계 정의 원칙과 보고서용 설명 문장은 아래 파일에 정리했다.

- `docs/boundary_definition_notes.md`

## 현재 해석상 주의점

- 판교 경계는 판교역 중심의 실질적 업무지구를 비교하기 위한 분석용 경계다.
- 등시시간권은 지하철 네트워크 최단시간과 역 주변 600m 서비스권을 결합한 근사 결과다.
- 최종 보고서 작성 전에는 판교 경계와 핵심역 설명 문장을 반드시 본문과 일치시켜야 한다.
