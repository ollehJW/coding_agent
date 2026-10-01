'use strict';
// Local interactive prototype. Replace task classification and question generation
// with an Agent API when a backend is connected; no requests leave this page.
const UNKNOWN = '아직 정하지 않았어요';
const taskProfiles = {
  reservation: {label:'예약·일정',keywords:['예약','회의실','장비 예약','일정','대여'],features:['날짜별 예약 현황 보기','예약 등록·취소','중복 예약 방지','예약 변경 알림'],rule:'예약은 어떤 방식으로 확정되면 좋을까요?',choices:['비어 있는 시간이면 바로 확정','담당자 승인 후 확정','담당자만 예약 등록'],data:'예약할 때 어떤 내용을 입력하나요?',dataHint:'예: 장비 이름, 예약 날짜와 시간, 신청자, 사용 목적',followValue:'담당자 승인 후 확정',follow:'누가 승인하고, 승인 전에는 시간이 어떻게 표시되나요?',followHint:'예: 장비 담당자 1명이 승인하고, 승인 대기는 다른 사람이 예약할 수 없게 표시',successHint:'예: 같은 장비를 같은 시간에 예약하면 중복 안내가 보이고, 빈 시간에는 예약이 완료돼요.'},
  report: {label:'보고서·문서',keywords:['보고','문서','주간','취합','보고서'],features:['자료 모아서 정리하기','정해진 양식으로 작성하기','내용 검토·수정하기','파일로 내려받기'],rule:'보고서에 쓸 내용은 어디에서 가져오나요?',choices:['화면에서 직접 입력','엑셀·CSV 파일 업로드','여러 문서를 모아서 사용','기존 사내 시스템에서 가져오기'],data:'완성된 보고서는 어떤 모습이면 좋을까요?',dataHint:'예: 팀원별 이번 주 실적과 다음 주 계획을 표로 정리한 문서. Word 파일로 다운로드',followValue:'엑셀·CSV 파일 업로드',follow:'엑셀에는 어떤 열이 있고, 어떻게 묶어야 하나요?',followHint:'예: 이름, 부서, 업무명, 실적, 계획이 있고 부서별로 묶고 싶어요.',successHint:'예: 팀원 10명의 입력이 빠짐없이 모이고, 고친 내용으로 보고서를 내려받을 수 있어요.'},
  inventory: {label:'재고·자산',keywords:['재고','입고','출고','자산','수량','물품'],features:['현재 수량 보기','입고·출고 기록하기','부족한 재고 표시하기','품목 검색하기'],rule:'재고 수량은 누가 바꿀 수 있나요?',choices:['담당자만 변경','모든 팀원이 변경','팀원 요청 후 담당자가 반영'],data:'품목별로 어떤 정보를 관리하나요?',dataHint:'예: 품목명, 품목 코드, 보관 위치, 현재 수량, 최소 보유 수량',followValue:'팀원 요청 후 담당자가 반영',follow:'출고 요청은 누가 확인하고, 언제 수량에서 빼나요?',followHint:'예: 창고 담당자가 실제 전달을 확인하면 수량에서 차감',successHint:'예: 출고를 기록하면 수량이 줄고, 재고보다 많은 출고는 저장되지 않아요.'},
  approval: {label:'신청·승인',keywords:['신청','승인','결재','접수'],features:['신청서 작성하기','진행 상태 확인하기','승인·반려 처리하기','이력 찾아보기'],rule:'신청 후 어떤 절차를 거치나요?',choices:['담당자 한 명이 확인','여러 담당자가 순서대로 승인','접수만 하고 별도 승인 없음'],data:'신청서에 어떤 정보를 적어야 하나요?',dataHint:'예: 신청자, 신청 날짜, 요청 내용, 첨부 자료',followValue:'여러 담당자가 순서대로 승인',follow:'승인 순서와 반려되었을 때의 처리 방법을 알려주세요.',followHint:'예: 파트장 → 팀장 순서로 승인하고, 반려되면 신청자가 수정 후 다시 제출',successHint:'예: 신청자는 자기 신청의 상태를 확인하고, 담당자는 승인 대기 건을 처리할 수 있어요.'},
  dashboard: {label:'현황·대시보드',keywords:['대시보드','차트','통계','현황','지표','시각화'],features:['주요 숫자 한눈에 보기','기간·부서별 조회','차트로 비교하기','원본 데이터 확인하기'],rule:'현황에 사용할 자료는 어디에 있나요?',choices:['엑셀·CSV 파일 업로드','화면에서 직접 입력','기존 사내 시스템에서 가져오기'],data:'꼭 보고 싶은 숫자와 비교 기준은 무엇인가요?',dataHint:'예: 월별 생산량과 불량률, 생산 라인별 비교. 이번 달과 지난달을 나란히 확인',followValue:'기존 사내 시스템에서 가져오기',follow:'어떤 시스템의 자료이며, 가져오는 방법을 알고 있나요?',followHint:'예: 사내 생산관리 시스템. 엑셀 내보내기는 가능하고 자동 연결 가능 여부는 몰라요.',successHint:'예: 기간을 바꾸면 표와 차트가 함께 바뀌고, 원본 자료의 합계와 일치해요.'},
  general: {label:'업무 도구',keywords:[],features:['내용 입력·수정하기','목록에서 찾아보기','결과를 파일로 받기','반복 작업 자동화하기'],rule:'사용자가 가장 먼저 하는 일은 무엇인가요?',choices:['새로운 내용을 입력','기존 자료를 업로드','목록에서 항목을 선택','버튼을 눌러 작업 시작'],data:'무엇을 입력하고, 어떤 결과를 얻고 싶나요?',dataHint:'예: 업무 목록을 입력하면 담당자별로 나눠서 보여주고 싶어요.',followValue:'기존 자료를 업로드',follow:'어떤 파일을 올리며, 그 안에는 어떤 내용이 있나요?',followHint:'예: 날짜, 담당자, 작업 내용이 있는 엑셀 파일',successHint:'예: 입력한 항목을 저장한 뒤 다시 찾아서 수정할 수 있으면 좋겠어요.'}
};
const examples = {
  reservation:{name:'공용 장비 예약 도구',description:'장비 예약을 메신저로 받고 있는데 자꾸 시간이 겹쳐요. 팀원들이 직접 예약하고 날짜별 현황을 볼 수 있는 도구를 만들고 싶어요.'},
  report:{name:'팀 주간보고 자동화',description:'팀원들의 주간 업무를 엑셀로 받아 매주 보고서로 옮겨 적고 있어요. 자료를 모아 같은 양식의 보고서로 만들고 싶어요.'},
  inventory:{name:'팀 물품 재고 관리',description:'공용 물품 재고를 엑셀로 관리해서 실제 수량과 자주 달라요. 입고와 출고를 기록하고 남은 수량을 쉽게 확인하고 싶어요.'}
};
let project = null, answers = {}, questionIndex = 0, manualEdited = false;
function notify(message){$('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3000);}
function setView(view){const isGuides=view==='guides';$('#definition-view').hidden=isGuides;$('#guides-view').hidden=!isGuides;document.querySelectorAll('[data-view]').forEach(button=>{const active=button.dataset.view===view;button.classList.toggle('active',active);if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});$('#breadcrumb-current').textContent=isGuides?'바이브코딩 가이드':'초기 프롬프트 만들기';$('#page-title').textContent=isGuides?'처음 만드는 업무 도구, 함께 시작해요.':'AI에게 뭐라고 말할지, 함께 만들어볼까요?';$('#page-description').textContent=isGuides?'DX추진랩의 개발 가이드와 작은 팁으로, 아이디어를 실행하는 방법을 알아보세요.':'하고 싶은 일을 알려주세요. 과제에 맞는 질문에 답하면, 첫 개발 요청에 쓸 프롬프트가 완성됩니다.';window.scrollTo(0,0);}
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>setView(button.dataset.view)));
$('#open-guides').addEventListener('click',()=>setView('guides'));$('#start-definition').addEventListener('click',()=>setView('definition'));
document.querySelectorAll('[data-example]').forEach(button=>button.addEventListener('click',()=>{const example=examples[button.dataset.example];$('#idea-name').value=example.name;$('#idea-description').value=example.description;$('#idea-description').setCustomValidity('');}));
function classifyTask(text){let best='general',score=0;Object.entries(taskProfiles).forEach(([key,profile])=>{const weight=profile.keywords.reduce((total,word)=>total+(text.includes(word)?word.length:0),0);if(weight>score){score=weight;best=key;}});return best;}
function questions(){if(!project)return [];const profile=taskProfiles[project.type];const list=[
  {id:'users',label:'사용자',title:'이 도구는 주로 누가 사용하나요?',help:'팀 규모나 담당자의 역할까지 알려주면 더 좋아요.',kind:'choice',options:['나 혼자 사용','우리 팀이 함께 사용','여러 부서가 함께 사용'],placeholder:'예: 생산기술팀 20명과 장비 담당자 1명'},
  {id:'features',label:'첫 버전 기능',title:'처음에는 어떤 기능부터 있으면 좋을까요?',help:'꼭 필요한 것만 골라주세요. 여러 개를 선택해도 괜찮아요.',kind:'multi',options:profile.features,placeholder:'선택지에 없는 기능이 있다면 적어주세요.'},
  {id:'rules',label:'업무 진행 방식',title:profile.rule,help:'현재 업무에서 자연스러운 방식을 선택해주세요.',kind:'choice',options:profile.choices,placeholder:'다른 방식이나 자세한 조건을 알려주세요.'}
];
if(answers.rules?.choices.includes(profile.followValue)&&!answers.rules.unknown)list.push({id:'followup',label:'추가 업무 규칙',title:profile.follow,help:'방금 답변에 맞춰 한 가지만 더 확인할게요.',kind:'text',placeholder:profile.followHint});
list.push(
  {id:'data',label:'입력과 결과',title:profile.data,help:'실제 데이터 대신 항목 이름이나 예시만 알려주셔도 돼요.',kind:'text',placeholder:profile.dataHint},
  {id:'environment',label:'사용 환경',title:'어디에서 사용할 도구인가요?',help:'환경에 따라 첫 화면과 실행 방법이 달라져요.',kind:'choice',options:['사내 PC의 웹 브라우저','내 PC에서 실행하는 도구','이미 쓰는 웹 서비스에 기능 추가'],placeholder:'예: 회사 PC, 기존 프로젝트 또는 필요한 기술이 있다면 적어주세요.'},
  {id:'success',label:'완료 기준',title:'어떻게 동작하면 “이제 쓸 만하다”고 느낄까요?',help:'확인해볼 수 있는 한 가지 장면을 적어주세요.',kind:'text',placeholder:profile.successHint},
  {id:'constraints',label:'추가 조건',title:'꼭 지켜야 할 조건이나, 이번에는 빼고 싶은 기능이 있나요?',help:'일정, 화면 스타일, 기존 서비스 연결 여부도 좋아요. 없으면 ‘특별한 조건 없음’이라고 적어주세요.',kind:'text',placeholder:'예: WiaReport와 비슷한 화면. PC에서만 사용하고 모바일·알림은 다음에 만들고 싶어요.'}
);return list;}
function answerText(answer){if(!answer)return '';if(answer.unknown)return UNKNOWN;return [...answer.choices,answer.text.trim()].filter(Boolean).join(' / ');}
function pruneAnswers(){const ids=new Set(questions().map(q=>q.id));Object.keys(answers).forEach(id=>{if(!ids.has(id))delete answers[id];});}
function setStage(stage){$('#idea-form').hidden=stage!==1;$('#survey-workspace').hidden=stage!==2;$('#survey-complete').hidden=stage!==3;$('#input-section-label').textContent=['START WITH YOUR IDEA','A FEW QUESTIONS FOR YOU','READY TO START'][stage-1];$('#idea-title').textContent=['어떤 도구를 만들고 싶으세요?','내 과제에 필요한 것부터, 하나씩.','나의 첫 개발 요청이 완성됐어요.'][stage-1];$('#input-step-label').textContent='STEP 0'+stage;['one','two','three'].forEach((name,index)=>$('#step-'+name).classList.toggle('active',index+1<=stage));}
function refreshSummary(){const list=questions();const completed=list.filter(q=>answerText(answers[q.id])).length;$('#survey-progress-text').textContent=`질문 ${questionIndex+1} / ${list.length} · ${completed}개 답변`;$('#survey-progress').setAttribute('aria-valuenow',String(Math.round(completed/list.length*100)));$('#survey-progress-fill').style.width=(completed/list.length*100)+'%';const container=$('#collected-answers');container.replaceChildren();list.forEach(q=>{const value=answerText(answers[q.id]);const row=document.createElement('div');row.className='collected-row'+(value?' answered':'');const label=document.createElement('span');label.textContent=q.label;const text=document.createElement('p');text.textContent=value||'질문에 답하면 이곳에 정리됩니다';row.append(label,text);container.append(row);});$('#next-question').innerHTML=(questionIndex===list.length-1?'초기 프롬프트 만들기':'다음 질문')+icon('arrow');}
function saveAnswer(){const q=questions()[questionIndex];if(!q)return;const text=$('#question-answer')?.value||'';const choices=[...document.querySelectorAll('#survey-question input:checked')].map(input=>input.value);answers[q.id]={text,choices,unknown:false};pruneAnswers();$('#unknown-answer').setAttribute('aria-pressed','false');$('#survey-error').hidden=true;refreshSummary();}
function renderQuestion(){const list=questions();questionIndex=Math.min(questionIndex,list.length-1);const q=list[questionIndex],answer=answers[q.id]||{choices:[],text:'',unknown:false};const container=$('#survey-question');container.replaceChildren();const index=document.createElement('span');index.className='question-eyebrow';index.textContent='QUESTION '+String(questionIndex+1).padStart(2,'0')+(q.id==='followup'?' · 답변에 따른 추가 질문':'');const title=document.createElement('h3');title.id='question-title';title.tabIndex=-1;title.textContent=q.title;const help=document.createElement('p');help.className='question-help';help.textContent=q.help;container.append(index,title,help);
if(q.options){const fieldset=document.createElement('fieldset');fieldset.className='answer-options';const legend=document.createElement('legend');legend.className='visually-hidden';legend.textContent=q.title;fieldset.append(legend);q.options.forEach((option,i)=>{const label=document.createElement('label');label.className='answer-option';const input=document.createElement('input');input.type=q.kind==='multi'?'checkbox':'radio';input.name='answer-choice';input.value=option;input.checked=!answer.unknown&&answer.choices.includes(option);input.id='choice-'+i;input.addEventListener('change',saveAnswer);const span=document.createElement('span');span.textContent=option;label.append(input,span);fieldset.append(label);});container.append(fieldset);}
const label=document.createElement('label');label.htmlFor='question-answer';label.className='question-input-label';label.textContent=q.options?'직접 적거나, 설명을 덧붙여도 좋아요':'내 답변';const textarea=document.createElement('textarea');textarea.id='question-answer';textarea.rows=q.options?2:5;textarea.maxLength=2000;textarea.placeholder=q.placeholder;textarea.value=answer.unknown?'':answer.text;textarea.addEventListener('input',saveAnswer);const unknown=document.createElement('button');unknown.type='button';unknown.id='unknown-answer';unknown.className='unknown-button';unknown.setAttribute('aria-pressed',String(answer.unknown));unknown.textContent='아직 모르겠어요 · 나중에 정할게요';unknown.addEventListener('click',()=>{if(answers[q.id]?.unknown){answers[q.id]={choices:[],text:'',unknown:false};}else{answers[q.id]={choices:[],text:'',unknown:true};}pruneAnswers();renderQuestion();});container.append(label,textarea,unknown);$('#previous-question').textContent=questionIndex===0?'과제 돌아보기':'이전 질문';$('#survey-error').hidden=true;refreshSummary();title.focus({preventScroll:true});}
function showSurvey(){setStage(2);$('#survey-project').textContent=project.name;$('#survey-type').textContent=taskProfiles[project.type].label+' 과제 · 맞춤 질문';$('#empty-result').hidden=true;$('#generated-result').hidden=true;$('#survey-summary').hidden=false;$('#copy-document').disabled=true;$('#download-document').disabled=true;$('#document-status').textContent='답변 정리 중';$('#document-status').classList.remove('ready');$('#document-hint').textContent='질문을 마치면 초기 프롬프트가 완성됩니다.';renderQuestion();}
$('#idea-form').addEventListener('submit',event=>{event.preventDefault();const description=$('#idea-description').value.trim();if(!description){$('#idea-description').setCustomValidity('만들고 싶은 내용을 한 문장으로 적어주세요.');$('#idea-description').reportValidity();return;}const name=$('#idea-name').value.trim()||'나의 업무 도구';if(project&&(project.description!==description||project.name!==name)){if(Object.keys(answers).length&&!confirm('과제가 바뀌면 새로운 서베이를 구성합니다. 기존 답변과 프롬프트를 초기화할까요?'))return;answers={};documentText='';manualEdited=false;questionIndex=0;}project={name,description,type:classifyTask(name+' '+description)};showSurvey();});
$('#idea-description').addEventListener('input',()=>$('#idea-description').setCustomValidity(''));
function returnToIdea(){setStage(1);$('#idea-title').focus?.({preventScroll:true});}
$('#change-idea').addEventListener('click',returnToIdea);
$('#previous-question').addEventListener('click',()=>{if(questionIndex===0)returnToIdea();else{questionIndex--;renderQuestion();}});
$('#survey-form').addEventListener('submit',event=>{event.preventDefault();const list=questions(),q=list[questionIndex];if(!answerText(answers[q.id])){$('#survey-error').hidden=false;$('#question-answer').focus();return;}if(questionIndex<list.length-1){questionIndex++;renderQuestion();}else finishSurvey();});
function buildPrompt(){const list=questions();const get=id=>answerText(answers[id])||UNKNOWN;const unresolved=list.filter(q=>!answers[q.id]||answers[q.id].unknown).map(q=>'- '+q.title);const knownRules=[get('rules'),answers.followup?'추가 규칙: '+get('followup'):''].filter(Boolean).join('\n');return `# ${project.name} — 바이브코딩 초기 프롬프트 / 개발 정의서

당신은 업무용 도구를 함께 만드는 개발 파트너입니다. 저는 개발 초심자입니다. 아래 요구사항으로 도구를 만들어주세요. 어려운 기술 용어는 쉬운 말로 설명하고, 한 번에 하나의 실행 가능한 단계씩 진행해주세요.

## 1. 만들고 싶은 것과 업무 배경
${project.description}

## 2. 사용 대상
${get('users')}

## 3. 첫 버전에서 필요한 기능
${get('features')}
선택한 기능을 바탕으로 핵심 업무 흐름부터 구현해주세요. 제가 요청하지 않은 기능은 임의로 추가하지 마세요.

## 4. 업무 진행 방식과 규칙
${knownRules}

## 5. 입력 자료와 원하는 결과
${get('data')}

## 6. 사용할 환경
${get('environment')}
기존 프로젝트가 있다면 구조와 기술을 먼저 확인하고 따르세요. 기술 구성이 정해지지 않았다면 이 업무에 맞는 간단한 구성을 제안하고 이유를 설명해주세요.

## 7. 완료되었다고 판단할 기준
${get('success')}
정상 사용 흐름과 빈 입력·잘못된 값 등 관련 예외 상황을 함께 확인해주세요. 위 기준을 확인할 수 있는 실행 방법과 테스트 순서를 알려주세요.

## 8. 추가 조건과 제외 범위
${get('constraints')}

## 9. 아직 결정하지 않은 내용
${unresolved.length?unresolved.join('\n'):'서베이의 모든 항목에 답변했습니다. 구현에 꼭 필요한 세부 정보가 빠졌다면 먼저 확인해주세요.'}
‘아직 정하지 않았어요’라고 적힌 내용은 요구사항으로 확정하지 마세요. 모르는 내용은 선택 가능한 방법과 차이를 쉽게 설명하고 질문해주세요. 실제 시스템 연동·배포·데이터 접근이 필요하면 연결 정보와 사용 조건을 먼저 확인해주세요.

## 10. 이렇게 시작해주세요
1. 제가 만들려는 도구와 핵심 사용자 흐름을 3~5문장으로 요약해주세요.
2. 답변끼리 모순되는 내용이 있거나 개발 방향을 결정하는 정보가 빠졌다면, 중요한 질문부터 최대 3개씩 확인해주세요. 이미 답한 내용은 다시 묻지 마세요.
3. 첫 버전의 화면, 핵심 기능, 작업 순서를 짧게 제안해주세요. 정해지지 않은 세부 사항은 가정임을 표시해주세요.
4. 중요한 질문이 해결되면 예시 데이터로 핵심 흐름의 첫 화면부터 구현해주세요. 기존 코드가 있으면 먼저 확인하고 이어서 작업해주세요.
5. 각 단계가 끝나면 실행 방법과 제가 확인할 항목을 알려주고, 결과를 확인하며 다음 기능을 진행해주세요.

이 프롬프트를 첫 개발 정의서로 삼아 함께 시작해주세요.`;}
function renderDocument(){const preview=$('#document-preview');preview.replaceChildren();documentText.split('\n').forEach(line=>{if(!line.trim())return;const heading=line.startsWith('## ')?2:line.startsWith('# ')?1:0;const node=document.createElement(heading?'h'+heading:'p');node.textContent=heading?line.slice(heading+1):line;preview.append(node);});}
function setDocumentTab(edit){$('#preview-tab').setAttribute('aria-selected',String(!edit));$('#edit-tab').setAttribute('aria-selected',String(edit));$('#preview-tab').tabIndex=edit?-1:0;$('#edit-tab').tabIndex=edit?0:-1;$('#document-preview').hidden=edit;$('#document-editor').hidden=!edit;if(edit)$('#document-editor').value=documentText;else renderDocument();}
function finishSurvey(){const missing=questions().findIndex(q=>!answerText(answers[q.id]));if(missing!==-1){questionIndex=missing;renderQuestion();return;}if(manualEdited&&!confirm('답변으로 다시 만들면 직접 수정한 프롬프트가 교체됩니다. 다시 만들까요?'))return;documentText=buildPrompt();documentName=project.name;manualEdited=false;setStage(3);$('#survey-summary').hidden=true;$('#empty-result').hidden=true;$('#generated-result').hidden=false;$('#document-status').textContent='프롬프트 완성';$('#document-status').classList.add('ready');$('#document-hint').textContent='복사 → 바이브코딩 도구에 붙여 넣기 → 개발 시작';$('#copy-document').disabled=false;$('#download-document').disabled=false;$('#edit-notice').textContent='서베이 답변을 바탕으로 작성했습니다';$('#answer-review').replaceChildren();questions().forEach(q=>{const row=document.createElement('div');const label=document.createElement('span');label.textContent=q.label;const text=document.createElement('p');text.textContent=answerText(answers[q.id]);row.append(label,text);$('#answer-review').append(row);});setDocumentTab(false);notify('초기 프롬프트가 완성됐어요. 복사해서 첫 개발 요청으로 사용하세요.');}
$('#review-answers').addEventListener('click',()=>{questionIndex=0;showSurvey();});
$('#preview-tab').addEventListener('click',()=>setDocumentTab(false));$('#edit-tab').addEventListener('click',()=>setDocumentTab(true));
document.querySelector('.document-tabs').addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const edit=event.key==='End'||(event.key!=='Home'&&document.activeElement.id==='preview-tab');setDocumentTab(edit);$(edit?'#edit-tab':'#preview-tab').focus();});
$('#document-editor').addEventListener('input',event=>{documentText=event.target.value;manualEdited=true;$('#edit-notice').textContent='수정 내용이 복사·다운로드에 반영됩니다';});
$('#download-document').addEventListener('click',()=>{const blob=new Blob(['\ufeff'+documentText],{type:'text/markdown;charset=utf-8'});const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=documentName.replace(/[\\/:*?"<>|\x00-\x1f]/g,'_')+'_초기프롬프트.md';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('초기 프롬프트를 Markdown 문서로 다운로드합니다.');});
$('#copy-document').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(documentText);notify('프롬프트를 복사했어요. 바이브코딩 도구에 붙여 넣어주세요.');}catch{setDocumentTab(true);$('#document-editor').focus();$('#document-editor').select();notify('Ctrl+C로 선택된 프롬프트를 복사해주세요.');}});
