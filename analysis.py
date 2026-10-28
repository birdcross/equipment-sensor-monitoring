"""Real dated MetroPT-3 measurements -> reproducible daily monitoring."""
from pathlib import Path
import json, hashlib, urllib.request, zipfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
SOURCE='https://archive.ics.uci.edu/static/public/791/metropt+3+dataset.zip'
PAGE='https://archive.ics.uci.edu/dataset/791/metropt+3+dataset'
SENSORS={'TP2':('압축기 압력','bar'),'TP3':('공압 패널 압력','bar'),'Oil_temperature':('오일 온도','°C'),'Motor_current':('모터 전류','A')}
EVENTS=[('2020-04-18 00:00','2020-04-18 23:59'),('2020-05-29 23:30','2020-05-30 06:00'),('2020-06-05 10:00','2020-06-07 14:30'),('2020-07-15 14:30','2020-07-15 19:00')]
def load():
    raw=ROOT/'data/raw';raw.mkdir(parents=True,exist_ok=True)
    archive=raw/'metropt3.zip'
    if not archive.exists():
        urllib.request.urlretrieve(SOURCE,archive.with_suffix('.part'))
        archive.with_suffix('.part').replace(archive)
    with zipfile.ZipFile(archive) as z:
        f=next(n for n in z.namelist() if n.endswith('.csv'))
        df=pd.read_csv(z.open(f),usecols=['timestamp',*SENSORS])
    df['timestamp']=pd.to_datetime(df['timestamp'],errors='raise')
    return df.sort_values('timestamp').set_index('timestamp'),archive

def aggregate(df,rule):
    out=df.resample(rule).agg(['mean','min','max','std','count'])
    out.columns=['_'.join(c) for c in out.columns]
    return out

def main():
    df,archive=load()
    assert not df.index.duplicated().any()
    assert np.isfinite(df.to_numpy()).all()
    daily=aggregate(df,'D');hourly=aggregate(df,'h')
    # Pad every calendar day to 24 hourly bins, including the last partial day.
    hourly=hourly.reindex(pd.date_range(daily.index.min(),daily.index.max()+pd.Timedelta(hours=23),freq='h',name='timestamp'))
    for table in (daily,hourly):
        table['assumed_off']=table['TP2_count'].fillna(0).eq(0)
        for sensor in SENSORS:
            for stat in ['mean','min','max','std','count']:
                col=sensor+'_'+stat
                table.loc[table.assumed_off,col]=0
        table['TP2_count']=table['TP2_count'].fillna(0)

    daily['samples']=daily.TP2_count
    daily['reported_failure']=False
    for a,b in EVENTS:
        daily.loc[(daily.index<=pd.Timestamp(b))&(daily.index+pd.Timedelta(days=1)>pd.Timestamp(a)),'reported_failure']=True
    for s in SENSORS:daily[s+'_ma7']=daily[s+'_mean'].rolling(7,min_periods=7).mean()
    daily.to_csv(ROOT/'data/daily_summary.csv',index_label='date')
    hourly.to_csv(ROOT/'data/hourly_summary.csv',index_label='timestamp')
    observed=daily[daily.samples>0];assert len(observed)>=100
    gaps=df.index.to_series().diff().dt.total_seconds().dropna()
    meta={'raw_rows':len(df),'start':str(df.index.min()),'end':str(df.index.max()),'calendar_days':len(daily),'observed_days':len(observed),'empty_days':int((daily.samples==0).sum()),'median_interval_seconds':float(gaps.median()),'max_gap_seconds':float(gaps.max()),'missing_cells':int(df.isna().sum().sum()),'duplicate_timestamps':0,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    (ROOT/'data/validation.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,'figure.figsize':(12,5)})
    for num,s in enumerate(['Oil_temperature','TP3','Motor_current'],1):
        fig,ax=plt.subplots(layout='constrained')
        ax.plot(daily.index,daily[s+'_mean'],color='#94a3b8',label='일별 평균')
        ax.plot(daily.index,daily[s+'_ma7'],color='#0891b2',label='7일 이동평균')
        for j,(a,b) in enumerate(EVENTS):ax.axvspan(pd.Timestamp(a).normalize(),pd.Timestamp(b).normalize()+pd.Timedelta(days=1),color='#ef4444',alpha=.13,label='보고된 공기 누설 기간' if j==0 else None)
        ax.set(title=SENSORS[s][0]+' 일별 추세',xlabel='원본 기록 날짜 (시간대 미지정)',ylabel=SENSORS[s][1]);ax.legend();ax.grid(alpha=.2)
        fig.savefig(ROOT/f'images/{num:02d}_daily_{s}.png',dpi=150);plt.close(fig)
    def records(table):return json.loads(table.reset_index().to_json(orient='records',date_format='iso',double_precision=5))
    payload={'dataset':'MetroPT-3','source':PAGE,'sensors':{s:{'name':n,'unit':u} for s,(n,u) in SENSORS.items()},'meta':meta,'daily':records(daily.rename_axis('date')),'hourly':records(hourly),'events':EVENTS}
    (ROOT/'dashboard/data.json').write_text(json.dumps(payload,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
    s='Oil_temperature_mean';peak=observed[s].idxmax();low=observed[s].idxmin()
    failure=observed[observed.reported_failure];other=observed[~observed.reported_failure]
    current=observed.Motor_current_mean;high=current.idxmax()
    report=f'''# 압축기 일별 상태 모니터링 분석 리포트

## 1. 주제와 선정 이유
실제 날짜가 포함된 MetroPT-3 압축기 센서 기록으로 장기간 운전 패턴과 공기 누설 보고 구간을 비교한다. 사출기·판금기의 실측 데이터가 아니라 열차 공기 생산 장치(APU)의 압축기 데이터다. 이전 60초 실험 데이터는 본 분석에 사용하지 않는다.

## 2. 분석 질문
1. 일별 평균 오일 온도와 7일 이동평균은 어떻게 변하는가?
2. 공기 누설이 보고된 날짜의 온도·압력·전류는 다른 날짜와 어떻게 다른가?
3. 하루 내부의 최솟값·최댓값과 시간대 패턴은 어떤 정보를 주는가?
4. 데이터 공백과 하루별 관측량 차이가 해석에 어떤 한계를 주는가?

## 3. 출처·기간·컬럼
- 출처: [UCI MetroPT-3]({PAGE}), DOI 10.24432/C5VW3R.
- 제작자: Davari, N., Veloso, B., Ribeiro, R., & Gama, J. (2021). 라이선스 CC BY 4.0. 원본 센서 기록을 일별·시간별로 가공했다.
- 실제 범위: **{df.index.min()} ~ {df.index.max()}**, 원본 {len(df):,}행.
- 전체 달력 {len(daily)}일 중 관측일 **{len(observed)}일**, 완전 공백 {(daily.samples==0).sum()}일. 원본 시간대가 명시되지 않아 한국 시간으로 변환하지 않았다.
- TP2 압축기 압력(bar), TP3 공압 패널 압력(bar), Oil_temperature 오일 온도(°C), Motor_current 모터 전류(A), timestamp 측정 시각.
- 공식 설명에는 원장치 1Hz 로깅과 공개본 0.1Hz가 모두 언급된다. 실제 인접 관측 중앙 간격은 {gaps.median():g}초, 최대 공백은 {gaps.max():,.0f}초다.

## 4. 정제·시계열 분석
- 날짜 파싱, 정렬, 중복 및 센서 결측·무한값을 검사했다. 선택 센서 결측·무한값 0개, 중복 시각 0개다.
- 사용자 지정 기준으로 관측이 전혀 없는 날짜·시간은 미가동으로 가정하고 센서 평균·최솟값·최댓값·표준편차를 0으로 채운다. assumed_off 열로 가정 여부를 보존한다. 원본 기록은 변경하지 않는다. 실제 정지나 실제 온도 0°C를 확인한 것은 아니다. 부분 관측 시간 내부의 짧은 공백은 추가로 0을 삽입하지 않는다.
- 극값은 기동·정지나 실제 이상을 담을 수 있어 삭제하지 않는다. 모든 값은 측정값이지 고장 판정이 아니다.
- 일별 평균·최솟값·최댓값·표준편차·관측 수를 산출한다. 하루 단위로 장기 흐름을 보되 순간 변화는 시간별 상세와 범위로 보완한다. 불규칙 공백을 고려한 시간가중 평균은 아니다.
- 7개 달력일 이동평균은 미가동 가정으로 채운 0도 포함한다. 최초 6일은 계산하지 않는다. 0 대체는 평균을 낮추므로 원본 관측 기반 통계와 구분한다.
- 추세는 장기 수준 변화, 계절성은 반복 시간 패턴, 노이즈는 불규칙 변동이다. 수개월 자료로 연간 계절성을 주장하지 않는다. 운영 조건·외기온도 영향을 줄 수 있다.
- 원 출처 공기 누설 보고 4개 구간과 겹친 날짜를 표시한다. 보고 없는 날짜를 검증된 정상으로 간주하지 않는다.

## 5. 시각화와 인사이트
### 5.1 오일 온도
![일별 오일 온도](images/01_daily_Oil_temperature.png)
- 관찰: 일평균 최고는 {peak.date()}의 {observed.loc[peak,s]:.2f}°C, 최저는 {low.date()}의 {observed.loc[low,s]:.2f}°C다.
- 해석(가설): 장기 수준 차이는 부하·주변 온도·정비·이상 상태가 복합적으로 작용한 결과일 수 있다. 높은 온도만으로 고장을 단정할 수 없다.
- 활용: 일별 평균과 7일 평균을 함께 보며 변화가 지속되는 구간을 상세 조회한다.

### 5.2 공압 패널 압력
![일별 공압 패널 압력](images/02_daily_TP3.png)
- 관찰: 보고 구간과 겹친 {len(failure)}일의 일평균 TP3 평균은 {failure.TP3_mean.mean():.3f}bar, 나머지 {len(other)}일은 {other.TP3_mean.mean():.3f}bar다. 날짜마다 같은 가중치를 부여했다.
- 해석(가설): 압력은 누설과 관련될 수 있지만 제어로 유지되거나 운전 조건에 좌우될 수도 있다. 보고일이 적고 하루 중 일부만 고장 구간이므로 단순 평균 비교의 한계가 크다.
- 활용: 보고일과 이전·이후 날짜의 시간별 최솟값·최댓값을 비교한다. 보고 표시는 예측 결과가 아니다.

### 5.3 모터 전류
![일별 모터 전류](images/03_daily_Motor_current.png)
- 관찰: 일평균 최고는 {high.date()}의 {current.max():.3f}A, 관측일 일평균 전류의 중앙값은 {current.median():.3f}A다.
- 해석(가설): 평균 전류 증가는 부하 운전 비중 또는 운전 스케줄 변화일 수 있다. 누설 원인으로 확정하려면 공기 수요·운전 모드를 함께 봐야 한다.
- 활용: 전류와 압력·온도를 함께 확인하고 해당 날짜의 시간별 기록을 점검한다.

## 6. 결론 및 한계
일별 전체 추세로 장기 변화를 확인하고 선택 날짜의 시간별 상세로 이동하는 구조다. 100일 이상 실제 날짜 기록을 확보했다. 일/시간 요약은 빠른 변화를 숨길 수 있어 최솟값·최댓값도 표시한다.
하나의 열차 압축기 기록이며 실제 공장 설비와 다르다. 운전 부하·외기온을 통제하지 않았다. 공백을 미가동으로 가정한 0은 관측 사실이 아니며 온도·압력의 실제 0을 뜻하지 않는다. 부분 관측일 평균은 원본 관측값 기준이다. 인사이트 수치는 관측이 있는 날짜만 사용한다. 미래 예측·인과효과는 검증하지 않았다. 사용자 설정에 따른 이상 후보 관리 기능은 있으나 실제 고장 감지 성능은 검증하지 않았다. 빨간 구간은 원 출처 보고를 재표시한 것이다.

## 7. AI 사용 로그
|작업|사용 이유|검증 방법|
|---|---|---|
|날짜 포함 설비 데이터 탐색|일별 분석 요건 충족|UCI 설명·라이선스·실제 timestamp 대조|
|집계·그래프·코드 작성|재현 가능한 분석|행 수·결측·중복·간격 검사, 원본 하루 재집계 검증|
|리포트 해석|관찰과 가설 구분|코드 계산 수치 사용, 보고일과 정상 라벨 구분|
|대시보드 작성|기간·날짜별 탐색|센서·기간·날짜 변경 동작 확인|

AI 초안이므로 제출자는 본인이 검토한 판단과 수정 사항을 추가해야 한다.

## 8. 재현 및 제출
본 문서의 실행 명령으로 원본·일별 CSV·시각화·보고서를 재생성한다. 대시보드에 전체 일별 그래프와 선택 날짜의 시간별 상세가 있다. 시계열 분해·예측 보너스와 GitHub 원격 게시, 보너스 제출용 스크린샷 세트는 별도 준비 사항이다.
'''
    document=ROOT/'README.md'
    marker='<!-- PROJECT_GUIDE_START -->'
    existing=document.read_text(encoding='utf-8') if document.exists() else ''
    guide=marker+existing.split(marker,1)[1] if marker in existing else ''
    analysis_part=report.split('## 8. 재현 및 제출')[0].rstrip()
    analysis_part=analysis_part.replace('# 압축기 일별 상태 모니터링 분석 리포트','# HYDRA — 설비 센서 분석 및 이상 수치 관리 리포트',1)
    # Preserve the actual conversation excerpts and verification log across regeneration.
    log_heading='## 7. AI 사용 로그'
    if log_heading in existing and marker in existing:
        saved_log=existing.split(log_heading,1)[1].split(marker,1)[0].rstrip()
        analysis_part=analysis_part.split(log_heading,1)[0]+log_heading+saved_log
    document.write_text(analysis_part+'\n\n'+guide+'\n',encoding='utf-8')
    print(json.dumps(meta,indent=2))
if __name__=='__main__':main()
