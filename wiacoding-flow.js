'use strict';
// Interactive mock: local conversation and task-specific card data, without an AI API.
let stage=1, project=null, draftType='general', questionIndex=0, answers={}, manualEdited=false;
const conversation=[];
const option=(title,description,reason)=>({title,description,reason});
const unsure=()=>option(UNKNOWN,'지금은 정하지 않고, AI와 함께 구체화합니다.','업무 방식이 아직 정해지지 않았다면 성급한 결정을 줄일 수 있어요.');
const featureDetails={
 approval:[['필요한 항목을 입력해 신청서를 제출해요.','제각각 받던 요청을 같은 형식으로 모을 수 있어요.'],['내 신청이 접수·검토·완료 중 어디에 있는지 확인해요.','진행 상황을 반복해서 문의하는 일을 줄일 수 있어요.'],['담당자가 신청을 승인하거나 반려 사유를 남겨요.','검토와 결정이 필요한 업무를 화면 안에서 처리할 수 있어요.'],['지난 신청과 처리 내역을 찾아볼 수 있어요.','과거 결정이나 결과를 다시 확인하는 업무에 적합해요.']],
 dashboard:[['중요한 지표를 한 화면에서 확인해요.','여러 자료를 열어 숫자를 찾는 시간을 줄이는 데 좋아요.'],['기간과 부서를 골라 해당 자료만 조회해요.','팀별·월별 비교가 자주 필요한 업무에 적합해요.'],['자료의 변화와 차이를 그래프로 보여줘요.','숫자만으로 파악하기 어려운 추세를 이해하는 데 좋아요.'],['집계 수치의 바탕이 되는 자료를 확인해요.','이상한 수치가 나왔을 때 원인을 찾아보기 좋아요.']],
 reservation:[['날짜와 장비별로 예약된 시간을 한눈에 확인해요.','예약 가능 시간을 찾는 일이 잦다면 먼저 현황을 보여주는 것이 좋아요.'],['팀원이 직접 예약을 만들고 취소할 수 있어요.','담당자가 대신 접수하는 반복 업무를 줄이고 싶을 때 좋아요.'],['이미 예약된 시간에는 새 예약을 저장하지 않아요.','예약 충돌이 주요 문제라면 업무 오류를 직접 줄일 수 있어요.'],['예약이 바뀌면 관련 사용자에게 알려줘요.','변경을 놓치는 일이 많을 때 좋아요. 알림을 보낼 방법은 별도 확인해요.']],
 report:[['여러 사람이 작성한 업무 내용을 한곳에 모아요.','자료를 찾아 복사하는 데 시간이 많이 들 때 시작하기 좋아요.'],['매번 같은 항목과 순서로 보고서 초안을 만들어요.','보고 양식이 정해져 있다면 반복되는 편집을 줄일 수 있어요.'],['생성한 초안을 화면에서 확인하고 고쳐요.','제출 전에 담당자의 검토가 필요한 업무에 적합해요.'],['완성한 내용을 문서 파일로 받아 공유해요.','기존 보고 절차에서 파일 제출을 요구할 때 유용해요.']],
 inventory:[['품목별로 지금 남아 있는 수량을 보여줘요.','재고를 문의하고 확인하는 시간을 줄이는 데 좋아요.'],['수량이 늘고 줄어든 이유와 시간을 기록해요.','실제 수량과 장부가 다르다면 변경 이력을 남기는 것이 좋아요.'],['정한 기준보다 수량이 적으면 화면에 표시해요.','필요한 물품이 떨어진 뒤 알게 되는 일을 줄이고 싶을 때 좋아요.'],['이름이나 코드로 원하는 품목을 찾아요.','관리하는 품목이 많아 목록을 찾기 어려울 때 유용해요.']],
 general:[['필요한 내용을 입력하고 나중에 수정해요.','흩어진 기록을 한곳에 모으는 작은 첫 버전에 적합해요.'],['기록한 내용을 목록과 검색으로 찾아요.','이전 자료를 찾는 데 시간이 오래 걸릴 때 유용해요.'],['정리된 결과를 파일로 저장해 사용해요.','다른 사람이나 기존 업무 도구로 결과를 전달할 때 좋아요.'],['반복되는 처리 작업을 버튼 하나로 실행해요.','처리 규칙이 명확하고 같은 작업을 자주 반복할 때 적합해요.']]
};
const dataOptions={
 approval:[option('기본 신청 정보','신청자, 신청 날짜, 요청 내용을 입력해요.','접수와 확인 흐름부터 작게 검증하기 좋아요.'),option('자료 첨부가 있는 신청','기본 정보와 함께 확인에 필요한 파일을 올려요.','담당자가 증빙이나 상세 자료를 검토해야 할 때 좋아요.'),option('신청 유형별 다른 항목','신청 종류를 고르면 관련 입력 항목이 나타나요.','여러 종류의 요청을 한곳에서 접수하는 업무에 적합해요.'),unsure()],
 dashboard:[option('핵심 지표의 합계','중요한 수치를 합계와 요약 숫자로 보여줘요.','현재 상태부터 빠르게 확인하는 첫 화면에 적합해요.'),option('기간별 변화','날짜나 월에 따른 지표의 변화를 비교해요.','성과가 나아지는지 흐름을 파악해야 할 때 좋아요.'),option('부서·항목별 비교','팀이나 품목별로 같은 지표를 나란히 비교해요.','차이가 나는 대상을 찾아 개선할 때 유용해요.'),unsure()],
 reservation:[option('예약 기본 정보','장비 이름, 날짜·시간, 신청자만 입력해요.','예약 흐름을 작게 시작하고 필요한 정보를 나중에 추가하기 좋아요.'),option('사용 목적까지 기록','기본 예약 정보에 사용 목적과 비고를 더해요.','장비를 어떻게 사용하는지 담당자가 확인해야 할 때 좋아요.'),option('프로젝트와 연결','예약 정보에 부서나 프로젝트 정보를 함께 남겨요.','여러 업무가 같은 장비를 사용할 때 사용 내역을 구분할 수 있어요.'),unsure()],
 report:[option('항목별 표로 정리','실적, 계획, 이슈를 정해진 표로 보여줘요.','기존 주간보고처럼 일정한 양식을 유지하기 좋아요.'),option('핵심 요약 보고서','주요 성과와 이슈를 짧은 문장으로 정리해요.','빠르게 핵심을 읽는 보고가 필요할 때 좋아요.'),option('화면과 파일 모두','화면에서 검토하고, 문서 파일로 내려받아요.','검토와 제출을 한 흐름으로 이어갈 수 있어요.'),unsure()],
 inventory:[option('품목과 수량 중심','품목명, 코드, 현재 수량을 관리해요.','단순한 재고 현황부터 빠르게 확인할 수 있어요.'),option('보관 위치 함께 관리','수량에 창고나 선반 위치를 함께 표시해요.','같은 물품을 여러 장소에 보관할 때 찾기 쉬워요.'),option('수량과 기준치 관리','현재 수량, 최소 수량, 입출고 이력을 기록해요.','재고 부족과 수량 차이를 함께 관리할 때 좋아요.'),unsure()],
 general:[option('입력 내용을 목록으로','직접 입력한 내용을 표 형태로 보여줘요.','입력과 확인이라는 기본 업무 흐름부터 검증하기 좋아요.'),option('파일을 읽고 결과 정리','기존 파일을 올리면 필요한 결과를 만들어요.','이미 파일로 관리하는 자료를 다시 입력하지 않아도 돼요.'),option('주요 수치를 차트로','자료를 집계해 숫자와 그래프로 보여줘요.','변화나 항목 간 차이를 빠르게 비교할 때 유용해요.'),unsure()]
};
function notify(text){$('#toast').textContent=text;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3500);}
function classify(text){let best='general',score=0;for(const [key,profile]of Object.entries(taskProfiles)){const value=profile.keywords.reduce((sum,word)=>sum+(text.includes(word)?word.length:0),0);if(value>score){best=key;score=value;}}return best;}
function setStage(next){stage=next;for(let i=1;i<=3;i++){const node=$('#flow-step-'+i);node.classList.toggle('active',i===next);node.classList.toggle('done',i<next);if(i===next)node.setAttribute('aria-current','step');else node.removeAttribute('aria-current');}$('#chat-stage').hidden=next!==1;$('#survey-stage').hidden=next!==2;$('#result-stage').hidden=next!==3;document.body.classList.toggle('focus-mode',next===2&&!$('#definition-view').hidden);$('#breadcrumb-current').textContent=['과제 정의','프롬프트 메이킹','초기 프롬프트'][next-1];}
function setView(view){const guide=view==='guides';$('#definition-view').hidden=guide;$('#guides-view').hidden=!guide;document.querySelectorAll('[data-view]').forEach(button=>{const active=button.dataset.view===view;button.classList.toggle('active',active);if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});setStage(stage);if(guide)$('#breadcrumb-current').textContent='바이브코딩 가이드';window.scrollTo(0,0);}
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>setView(button.dataset.view)));
$('#open-guides').addEventListener('click',()=>setView('guides'));$('#start-definition').addEventListener('click',()=>setView('definition'));
function addMessage(role,text){conversation.push({role,text});const row=document.createElement('div');row.className='chat-message '+role;if(role==='assistant'){const badge=document.createElement('span');badge.className='agent-emblem';badge.innerHTML=icon('spark');row.append(badge);}const content=document.createElement('div');content.className='chat-message-content';const name=document.createElement('span');name.className='chat-message-name';name.textContent=role==='assistant'?'WiaCoding':'나';const message=document.createElement('p');message.textContent=text;content.append(name,message);row.append(content);$('#chat-messages').append(row);$('#chat-messages').scrollTop=$('#chat-messages').scrollHeight;}
function userMessages(){return conversation.filter(m=>m.role==='user').map(m=>m.text);}
const contextAnswers={};
const definitionFields=['name','background','users','scope','objective'];
const contextSteps=[
 {id:'problem',question:'안녕하세요. WiaCoding이에요.\n바로 무엇을 만들지 정하기 전에, 지금 업무에서 어떤 문제가 있는지 알아볼게요.\n\n어떤 문제를 해결하고 싶으세요?',options:[['장비 예약이 자꾸 겹쳐요','팀원들끼리 같은 시간에 장비를 예약하는 일이 생겨요.'],['예약 현황을 찾기 어려워요','누가 언제 쓰는지 매번 담당자에게 물어봐야 해요.'],['예약 변경을 놓쳐요','메신저로 오가는 취소나 변경 사항이 누락돼요.']]},
 {id:'current',question:'어떤 문제인지 알겠어요. 원인을 이해하려면 현재 업무 방식도 알아야 해요.\n\n지금은 장비 예약을 어떻게 받고 관리하고 있나요?',options:[['메신저로 받고 엑셀에 정리해요','담당자가 요청을 받아 예약표에 직접 옮겨 적고 있어요.'],['공유 엑셀에 직접 적어요','팀원들이 같은 파일을 열어 예약 정보를 수정해요.'],['담당자에게 구두로 요청해요','담당자가 요청을 기억하거나 따로 메모해서 관리해요.']]},
 {id:'impact',question:'현재 흐름을 이해했어요. 다음으로, 이 문제가 실제 업무에 어떤 영향을 주는지 확인할게요.\n\n가장 불편한 순간이나 반복해서 생기는 일은 무엇인가요?',options:[['중복 예약으로 작업이 지연돼요','예약 시간이 겹쳐 한 팀이 기다리거나 일정을 다시 조정해요.'],['확인과 정리에 시간이 들어요','담당자가 같은 문의에 답하고 예약표를 계속 정리해요.'],['변경 내용을 다시 확인해야 해요','예약표와 실제 사용 상황이 달라 여러 번 확인하게 돼요.']]},
 {id:'users',question:'업무에 어떤 영향을 주는지 알겠어요. 누가 이 문제를 겪는지도 알아볼게요.\n\n주로 누가 장비를 사용하고, 누가 예약을 관리하나요?',options:[['팀원 20명과 장비 담당자 1명','팀원들이 장비를 사용하고 담당자 한 명이 예약을 정리해요.'],['여러 부서가 함께 사용해요','여러 팀이 공용 장비를 쓰고 운영 담당자가 관리해요.'],['소규모 팀이 직접 관리해요','5명 안팎의 팀원이 함께 사용하며 예약도 직접 정리해요.']]},
 {id:'goal',question:'사용자와 담당자까지 파악했어요. 마지막으로, 이번 과제를 통해 어떤 변화가 생기면 좋을지 정해볼게요.\n\n가장 먼저 바꾸고 싶은 모습은 무엇인가요?',options:[['팀원이 빈 시간을 보고 직접 예약해요','예약 현황을 확인하고, 시간이 겹치지 않을 때 직접 등록하면 좋겠어요.'],['담당자가 한 화면에서 관리해요','요청과 변경을 모아서 보고 예약을 확정할 수 있으면 좋겠어요.'],['예약과 실제 사용 이력을 남겨요','변경·취소와 실제 사용 내역을 쉽게 확인할 수 있으면 좋겠어요.']]}
];
function renderContextQuestion(){const index=Object.keys(contextAnswers).length;if(index>=contextSteps.length)return;const step=contextSteps[index];addMessage('assistant',step.question);const content=$('#chat-messages').lastElementChild.querySelector('.chat-message-content');const choices=document.createElement('div');choices.className='context-choices';choices.setAttribute('role','group');choices.setAttribute('aria-label','답변 선택지');step.options.forEach(([title,description],i)=>{const button=document.createElement('button');button.type='button';button.className='context-choice';const top=document.createElement('strong');top.textContent=title;const detail=document.createElement('span');detail.textContent=description;button.append(top,detail);if(i===0){const tag=document.createElement('small');tag.textContent='예제로 계속하기';button.append(tag);}button.addEventListener('click',()=>sendMessage(title+'\n'+description));choices.append(button);});content.append(choices);$('#chat-input').placeholder='선택지를 고르거나 '+['해결할 문제','현재 업무 방식','불편한 점','사용자와 담당자','원하는 변화'][index]+'를 직접 적어주세요.';$('#chat-messages').scrollTop=$('#chat-messages').scrollHeight;}
function completeDefinition(){draftType='reservation';$('#context-status').textContent='배경 정리 완료';$('#chat-form').hidden=true;$('#task-proposal').hidden=false;$('#chat-stage').classList.add('definition-ready');$('#task-name').value='공용 장비 예약 관리 개선';$('#task-background').value='해결할 문제: '+contextAnswers.problem+'\n\n현재 업무: '+contextAnswers.current+'\n\n불편과 영향: '+contextAnswers.impact;$('#task-users').value=contextAnswers.users;$('#task-scope').value='공용 장비의 예약 관리 흐름을 우선 개선합니다. 세부 기능과 운영 규칙은 다음 단계에서 정합니다.';$('#task-objective').value=contextAnswers.goal;addMessage('assistant','해결할 문제, 현재 업무 방식, 불편한 점, 사용자, 원하는 변화까지 파악했어요.\n이제 과제를 정리할 수 있겠습니다.\n\n대화 내용을 바탕으로 아래에 과제 정의를 작성했어요. 원하는 방향과 맞는지 살펴보고, 수정한 뒤 확정해주세요.');$('#task-proposal').scrollIntoView({behavior:'smooth',block:'start'});}
function sendMessage(text){const value=text.trim(),index=Object.keys(contextAnswers).length;if(!value||index>=contextSteps.length)return;const step=contextSteps[index];$('#chat-messages').querySelectorAll('.context-choice').forEach(button=>button.disabled=true);addMessage('user',value);contextAnswers[step.id]=value;const chip=document.querySelector('[data-context="'+step.id+'"]');chip.classList.add('collected');chip.setAttribute('aria-label',chip.textContent+' 수집 완료');$('#chat-input').value='';$('#chat-input').setCustomValidity('');if(index+1===contextSteps.length)completeDefinition();else{renderContextQuestion();$('#chat-input').focus({preventScroll:true});}}
$('#chat-form').addEventListener('submit',event=>{event.preventDefault();const input=$('#chat-input');if(!input.value.trim()){input.setCustomValidity('업무 문제나 답변을 적어주세요.');input.reportValidity();return;}sendMessage(input.value);});
$('#chat-input').addEventListener('input',()=>$('#chat-input').setCustomValidity(''));
$('#chat-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('#chat-form').requestSubmit();}});
function draftSignature(){return JSON.stringify({...Object.fromEntries(definitionFields.map(key=>[key,$('#task-'+key).value.trim()])),messages:userMessages()});}
for(const key of definitionFields)$('#task-'+key).addEventListener('input',()=>{$('#task-'+key).setCustomValidity('');$('#resume-survey').hidden=!project||project.signature!==draftSignature();});
$('#confirm-task').addEventListener('click',()=>{if(Object.keys(contextAnswers).length!==contextSteps.length)return;for(const key of definitionFields){const field=$('#task-'+key);if(!field.value.trim()){field.setCustomValidity('과제 정의 내용을 입력해주세요.');field.reportValidity();return;}}const signature=draftSignature();if(project&&signature!==project.signature&&Object.keys(answers).length&&!confirm('과제가 바뀌면 기존 서베이 답변과 프롬프트가 초기화됩니다. 수정한 과제로 진행할까요?'))return;if(!project||signature!==project.signature){project={...Object.fromEntries(definitionFields.map(key=>[key,$('#task-'+key).value.trim()])),type:'reservation',messages:userMessages(),signature};answers={};questionIndex=0;documentText='';manualEdited=false;}setStage(2);renderQuestion();window.scrollTo(0,0);});
$('#resume-survey').addEventListener('click',()=>{setStage(2);renderQuestion();window.scrollTo(0,0);});
$('#back-to-chat').addEventListener('click',()=>{setStage(1);$('#resume-survey').hidden=!project||project.signature!==draftSignature();$('#task-proposal').scrollIntoView({behavior:'smooth',block:'start'});});
function ruleOptions(profile){const descriptions={
 '비어 있는 시간이면 바로 확정':['빈 시간을 고르면 별도 승인 없이 예약이 완료돼요.','승인 과정이 필요 없는 팀이라면 가장 짧은 예약 흐름으로 시작할 수 있어요.'],
 '담당자 승인 후 확정':['신청 내용을 담당자가 확인한 뒤 예약을 확정해요.','사용 자격이나 목적을 확인해야 하는 장비에 적합해요.'],
 '담당자만 예약 등록':['담당자가 요청을 받아 예약 내용을 등록해요.','예약 운영 권한을 한곳에서 관리해야 할 때 좋아요.'],
 '화면에서 직접 입력':['사용자가 화면에 필요한 내용을 직접 작성해요.','파일 양식을 맞추는 과정 없이 입력 흐름부터 확인할 수 있어요.'],
 '엑셀·CSV 파일 업로드':['기존 표 파일을 올려 안의 내용을 가져와요.','이미 엑셀로 일하고 있다면 입력을 반복하지 않아도 돼요.'],
 '여러 문서를 모아서 사용':['여러 문서의 내용을 읽고 한곳에 정리해요.','자료가 문서마다 흩어져 있을 때 유용해요. 문서 구조 확인이 필요해요.'],
 '기존 사내 시스템에서 가져오기':['사용 중인 시스템의 데이터와 연결해요.','원본을 계속 관리하는 시스템이 있다면 중복 관리를 줄일 수 있어요.'],
 '담당자만 변경':['지정한 담당자가 수량을 수정하고 기록해요.','기록 책임을 명확하게 하고 변경을 통제할 때 적합해요.'],
 '모든 팀원이 변경':['팀원이 직접 사용한 수량을 기록해요.','사용 현장에서 바로 기록해 누락을 줄이고 싶을 때 좋아요.'],
 '팀원 요청 후 담당자가 반영':['팀원은 요청하고 담당자가 확인해 수량에 반영해요.','실제 물품 전달을 확인한 뒤 장부를 바꾸는 업무에 적합해요.']};
const list=profile.choices.map(title=>{const info=descriptions[title]||[`${title} 방식으로 업무의 첫 흐름을 구성해요.`,`현재 업무가 ‘${title}’ 방식이라면 익숙한 순서를 유지할 수 있어요.`];return option(title,...info);});while(list.length<4)list.push(unsure());return list.slice(0,4);}
function followOptions(){
 if(project.type==='general')return [option('엑셀·CSV 표 파일','행과 열로 정리된 업무 자료를 올려요.','정해진 항목의 데이터를 반복 처리하는 과제에 좋아요.'),option('텍스트 문서','문장으로 작성한 업무 내용을 올려요.','문서 내용을 정리하거나 필요한 정보를 찾는 과제에 적합해요.'),option('여러 종류의 파일','서로 다른 형식의 자료를 함께 사용해요.','자료가 다양한 형태로 들어오는 업무에 맞아요. 형식별 확인이 필요해요.'),unsure()];
 if(project.type==='inventory')return [option('실제 전달 후 차감','담당자가 물품 전달을 확인한 뒤 수량을 줄여요.','장부와 실물의 수량을 함께 맞추는 데 좋아요.'),option('요청 승인 시 차감','출고 요청을 승인하는 순간 수량을 줄여요.','승인과 물품 전달이 같은 시점에 이뤄지는 업무에 적합해요.'),option('예약 수량을 별도 표시','승인된 물품은 예약으로 두고 실제 출고 때 차감해요.','승인과 실제 전달 사이에 시간이 있는 업무에 적합해요.'),unsure()];if(project.type==='report')return [option('팀원별 업무 자료','이름, 업무명, 실적, 계획을 팀원별로 묶어요.','팀원의 주간 업무를 빠짐없이 취합하기 좋아요.'),option('부서별 실적 자료','부서, 기간, 성과를 기준으로 묶어요.','여러 팀의 성과를 비교하는 보고에 적합해요.'),option('프로젝트별 진행 자료','프로젝트, 담당자, 진행률, 이슈로 정리해요.','개별 업무보다 프로젝트 진행 상황이 중요할 때 좋아요.'),unsure()];if(project.type==='dashboard')return [option('엑셀 내보내기 가능','시스템에서 내보낸 파일을 먼저 사용해요.','시스템을 직접 연결하지 않고도 현황 화면을 검증할 수 있어요.'),option('연결 방법을 알고 있음','사용 가능한 데이터 연결 방법을 알려줄 수 있어요.','접근 조건이 확인된 경우 자동 갱신을 검토할 수 있어요.'),option('담당자에게 확인 필요','연결 방법과 사용 권한을 먼저 확인해요.','잘 모르는 시스템 구조를 임의로 가정하지 않도록 해요.'),unsure()];return [option('담당자 1명이 확인','지정 담당자가 내용을 확인하고 처리해요.','한 단계의 책임이 명확한 승인 흐름으로 작게 시작하기 좋아요.'),option('여러 담당자가 순서대로','이전 승인 후 다음 담당자에게 넘어가요.','실제 업무에 여러 승인 단계가 필요한 경우에 적합해요.'),option('담당자 중 한 명이 확인','지정된 담당자 중 누구나 처리할 수 있어요.','담당자 부재로 처리가 지연되는 것을 줄이고 싶을 때 좋아요.'),unsure()];}
function questions(){if(!project)return [];const p=taskProfiles[project.type],details=featureDetails[project.type]||featureDetails.general;const list=[
 {id:'users',label:'사용자',title:'이 도구는 주로 누가 사용하나요?',help:'사용 범위를 정하면, 첫 버전의 화면과 권한을 더 간단하게 잡을 수 있어요.',cards:[option('우리 팀이 함께 사용','팀원들이 같은 자료를 보고 업무를 나눠서 사용해요.','팀 안의 반복 업무부터 개선하는 작은 첫 과제에 적합해요.'),option('나 혼자 사용','내 업무를 편하게 만드는 개인용 도구로 시작해요.','협업과 권한 설정을 줄이고 핵심 기능에 집중할 수 있어요.'),option('여러 부서가 함께 사용','부서마다 필요한 업무와 자료를 함께 관리해요.','여러 팀이 같은 정보를 주고받아야 하는 과제에 적합해요.'),option('담당자가 대신 운영','담당자가 입력·관리하고 다른 사람은 결과를 확인해요.','모든 사용자에게 입력 권한을 주기 어려운 업무에 좋아요.')]},
 {id:'features',label:'첫 버전 기능',title:'처음에는 어떤 기능부터 있으면 좋을까요?',help:'여러 개를 선택할 수 있어요. 첫 버전에 꼭 필요한 것부터 골라주세요.',multi:true,cards:p.features.map((title,i)=>option(title,...details[i]))},
 {id:'rules',label:'업무 방식',title:p.rule,help:'현재 업무에 맞는 방식을 선택해주세요. 선택한 방식에 따라 추가 질문이 나올 수 있어요.',cards:ruleOptions(p)}];
if(answers.rules?.selected.includes(p.followValue))list.push({id:'followup',label:'답변에 따른 추가 질문',title:p.follow,help:'방금 선택한 업무 방식에 맞춰 조금 더 구체화할게요. 자세한 내용은 Custom Answer에 적어주세요.',cards:followOptions()});
list.push(
 {id:'data',label:'입력과 결과',title:p.data,help:'처음부터 모든 정보를 넣기보다, 업무에 꼭 필요한 정보부터 정해보세요.',cards:dataOptions[project.type]||dataOptions.general},
 {id:'environment',label:'사용 환경',title:'어디에서 사용할 도구인가요?',help:'개발 언어를 몰라도 괜찮아요. 실제 사용할 환경만 골라주세요.',cards:[option('사내 PC의 웹 브라우저','별도 프로그램 설치 없이 PC 브라우저에서 열어요.','여러 팀원이 같은 화면으로 접속하는 업무 도구에 적합해요.'),option('내 PC에서 실행','내 컴퓨터에서 실행하는 개인용 도구로 만들어요.','개인 파일 처리처럼 한 사람의 업무를 도울 때 좋아요.'),option('기존 서비스에 기능 추가','이미 사용하는 프로젝트나 서비스에 기능을 더해요.','기존 화면과 기술을 유지하며 개선해야 하는 경우에 적합해요.'),unsure()]},
 {id:'success',label:'완료 기준',title:'어떻게 동작하면 첫 버전이 완성된 걸까요?',help:'직접 사용해보며 확인할 수 있는 기준을 골라주세요. 구체적인 장면을 적어주셔도 좋아요.',cards:[option('핵심 업무가 끝까지 동작','입력부터 결과 확인까지 실제 업무 순서로 사용해요.','첫 버전이 업무에 도움이 되는지 가장 직접적으로 확인할 수 있어요.'),option('기존 자료와 결과가 일치','예시 자료를 넣어 기존 결과와 같은지 비교해요.','집계·보고처럼 결과의 정확도가 중요한 업무에 적합해요.'),option('반복 작업 시간이 줄어듦','같은 작업을 이전보다 적은 단계로 처리해요.','반복 입력이나 자료 이동이 주요 문제일 때 효과를 확인하기 좋아요.'),unsure()]},
 {id:'constraints',label:'첫 버전 범위',title:'첫 개발에서 우선 지킬 조건이 있나요?',help:'작게 완성하기 위한 기준이에요. 꼭 필요한 조건이나 제외할 기능을 직접 덧붙여주세요.',cards:[option('PC 화면의 핵심 기능부터','모바일·알림 같은 부가 기능은 다음에 만들어요.','첫 과제의 범위를 줄여 업무 흐름을 빠르게 확인하기 좋아요.'),option('기존 서비스 스타일 유지','기존 업무 도구와 비슷한 화면으로 구성해요.','사용자가 새 화면에 적응하는 부담을 줄일 수 있어요.'),option('예시 데이터로 먼저 검증','실제 시스템 연결 전에 화면과 동작을 확인해요.','데이터 연결 조건을 확인하는 동안에도 아이디어를 검증할 수 있어요.'),option('아직 특별한 조건 없음','추가 조건은 개발을 진행하며 정리해요.','지금 정해진 제약이 없다면 우선 핵심 흐름부터 시작할 수 있어요.')]} );return list;}
function answerText(answer){return answer?[...answer.selected,answer.custom.trim()].filter(Boolean).join('\n'):'';}
function saveAnswer(){const q=questions()[questionIndex];answers[q.id]={selected:[...document.querySelectorAll('#answer-cards input:checked')].map(input=>input.value),custom:$('#custom-answer').value};const ids=new Set(questions().map(item=>item.id));Object.keys(answers).forEach(id=>{if(!ids.has(id))delete answers[id];});$('#survey-error').hidden=true;updateProgress();}
function updateProgress(){const list=questions(),done=list.filter(q=>answerText(answers[q.id])).length;$('#survey-count').textContent=`QUESTION ${String(questionIndex+1).padStart(2,'0')} / ${String(list.length).padStart(2,'0')}`;$('#survey-answered').textContent=`${done}개 답변`;const pct=Math.round(done/list.length*100);$('#survey-progress').setAttribute('aria-valuenow',String(pct));$('#survey-progress-fill').style.width=pct+'%';$('#next-question').innerHTML=(questionIndex===list.length-1?'초기 프롬프트 완성하기':'다음 질문')+icon('arrow');}
function renderQuestion(){const list=questions();questionIndex=Math.min(questionIndex,list.length-1);const q=list[questionIndex],answer=answers[q.id]||{selected:[],custom:''};$('#survey-project').textContent=project.name;$('#question-category').textContent=q.label+(q.multi?' · 복수 선택':' · 하나 선택');$('#question-title').textContent=q.title;$('#question-description').textContent=q.help;const cards=$('#answer-cards');cards.replaceChildren();const legend=document.createElement('legend');legend.className='visually-hidden';legend.textContent=q.title;cards.append(legend);q.cards.forEach((choice,i)=>{const label=document.createElement('label');label.className='answer-card'+(i===0?' recommended':'');const top=document.createElement('span');top.className='answer-card-top';const letter=document.createElement('span');letter.className='answer-letter';letter.textContent=String.fromCharCode(65+i);top.append(letter);if(i===0){const badge=document.createElement('span');badge.className='answer-recommended';badge.textContent='시작점 추천';top.append(badge);}const input=document.createElement('input');input.type=q.multi?'checkbox':'radio';input.name='survey-choice';input.value=choice.title;input.checked=answer.selected.includes(choice.title);input.setAttribute('aria-label',choice.title);input.addEventListener('change',saveAnswer);top.append(input);const title=document.createElement('span');title.className='answer-card-title';title.textContent=choice.title;const desc=document.createElement('span');desc.className='answer-card-description';desc.textContent=choice.description;const reason=document.createElement('span');reason.className='answer-card-reason';reason.innerHTML=icon('spark');const copy=document.createElement('span');const reasonLabel=document.createElement('strong');reasonLabel.textContent='추천 이유';copy.append(reasonLabel,document.createTextNode(choice.reason));reason.append(copy);label.append(top,title,desc,reason);cards.append(label);});$('#custom-answer').value=answer.custom;$('#survey-error').hidden=true;$('#previous-question').textContent=questionIndex===0?'과제 정의로':'이전 질문';updateProgress();$('#question-title').focus({preventScroll:true});}
$('#custom-answer').addEventListener('input',saveAnswer);$('#clear-choices').addEventListener('click',()=>{document.querySelectorAll('#answer-cards input').forEach(input=>input.checked=false);saveAnswer();});
$('#previous-question').addEventListener('click',()=>{if(questionIndex===0){$('#back-to-chat').click();return;}questionIndex--;renderQuestion();});
$('#survey-form').addEventListener('submit',event=>{event.preventDefault();if(!answerText(answers[questions()[questionIndex].id])){$('#survey-error').hidden=false;$('#custom-answer').focus();return;}if(questionIndex<questions().length-1){questionIndex++;renderQuestion();window.scrollTo(0,0);}else finish();});
function buildPrompt(){const get=id=>answerText(answers[id])||UNKNOWN;const unknown=questions().filter(q=>answers[q.id]?.selected.includes(UNKNOWN)).map(q=>'- '+q.title);return `# ${project.name} — 초기 개발 프롬프트 / 개발 정의서

당신은 업무용 도구를 함께 만드는 개발 파트너입니다. 저는 개발 초심자입니다. 아래 과제와 요구사항을 바탕으로 도구를 만들어주세요. 기술 용어는 쉽게 설명하고, 하나의 실행 가능한 단계씩 진행해주세요.

## 1. 대화로 정의한 과제
과제명: ${project.name}
목표와 기대하는 변화: ${project.objective}

확정한 업무 배경:
${project.background}

확정한 사용자와 담당자:
${project.users}

첫 과제 범위:
${project.scope}

업무 담당자가 대화에서 설명한 배경과 추가 맥락:
${project.messages.map((text,i)=>`${i+1}. ${text}`).join('\n')}
이 대화는 요구사항을 이해하기 위한 참고 자료입니다. 수정된 최종 과제 목표를 우선하고, 서로 모순되는 내용은 먼저 확인해주세요.

## 2. 누가 사용하는가
${get('users')}

## 3. 첫 버전의 기능
${get('features')}
먼저 선택한 기능의 핵심 업무 흐름을 구현해주세요. 요청하지 않은 부가 기능은 임의로 추가하지 마세요.

## 4. 업무 방식과 규칙
${get('rules')}${answers.followup?'\n추가 규칙:\n'+get('followup'):''}

## 5. 입력 자료와 결과
${get('data')}

## 6. 사용 환경
${get('environment')}
기존 프로젝트가 있으면 구조와 기술을 먼저 확인하고 따르세요. 새로운 기술을 정해야 한다면 간단한 구성을 제안하고 이유를 설명해주세요.

## 7. 완료 기준
${get('success')}
이 기준에 맞춰 직접 확인할 수 있는 시나리오와 실행 방법을 알려주세요. 정상 흐름과 빈 입력·잘못된 값 등 관련 예외 상황을 확인해주세요.

## 8. 추가 조건과 제외 범위
${get('constraints')}

## 9. 확인이 필요한 내용
${unknown.length?unknown.join('\n'):'선택한 답변과 직접 입력한 설명에서 개발에 필요한 정보가 빠졌다면 확인해주세요.'}
선택지와 직접 입력한 설명이 모순되면 임의로 결정하지 말고 질문해주세요. ‘아직 정하지 않았어요’는 확정된 요구사항이 아닙니다. 자료 연결이나 배포에 필요한 정보와 사용 조건도 확인해주세요.

## 10. 첫 개발 요청
1. 이해한 과제와 핵심 사용자 흐름을 3~5문장으로 요약해주세요.
2. 개발 방향을 결정하는 정보가 빠졌다면 중요한 질문부터 최대 3개씩 물어보세요. 이미 답한 내용은 반복해서 묻지 마세요.
3. 첫 버전의 화면, 필요한 기능, 작업 순서를 짧게 제안해주세요.
4. 중요한 질문이 해결되면 핵심 업무 흐름의 첫 화면부터 구현해주세요. 기존 코드가 있다면 먼저 확인하고 이어서 작업해주세요.
5. 단계마다 실행 방법과 확인할 항목을 알려주고, 결과를 확인하며 다음 단계로 진행해주세요.

이 초기 프롬프트를 개발 정의서로 삼아 함께 시작해주세요.`;}
function renderDocument(){const preview=$('#document-preview');preview.replaceChildren();documentText.split('\n').filter(line=>line.trim()).forEach(line=>{const level=line.startsWith('## ')?2:line.startsWith('# ')?1:0;const node=document.createElement(level?'h'+level:'p');node.textContent=level?line.slice(level+1):line;preview.append(node);});}
function setDocumentTab(edit){$('#preview-tab').setAttribute('aria-selected',String(!edit));$('#edit-tab').setAttribute('aria-selected',String(edit));$('#preview-tab').tabIndex=edit?-1:0;$('#edit-tab').tabIndex=edit?0:-1;$('#document-preview').hidden=edit;$('#document-editor').hidden=!edit;if(edit)$('#document-editor').value=documentText;else renderDocument();}
function finish(){const missing=questions().findIndex(q=>!answerText(answers[q.id]));if(missing>=0){questionIndex=missing;renderQuestion();return;}if(manualEdited&&!confirm('답변으로 다시 만들면 직접 수정한 프롬프트가 교체됩니다. 계속할까요?'))return;documentText=buildPrompt();documentName=project.name;manualEdited=false;$('#document-name').textContent=project.name;$('#edit-notice').textContent='복사 전 내용을 확인해주세요';setStage(3);setDocumentTab(false);window.scrollTo(0,0);notify('초기 프롬프트가 완성됐어요. 복사해서 첫 개발 요청으로 사용하세요.');}
$('#review-answers').addEventListener('click',()=>{questionIndex=0;setStage(2);renderQuestion();window.scrollTo(0,0);});
$('#preview-tab').addEventListener('click',()=>setDocumentTab(false));$('#edit-tab').addEventListener('click',()=>setDocumentTab(true));
document.querySelector('.document-tabs').addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const edit=event.key==='End'||(event.key!=='Home'&&document.activeElement.id==='preview-tab');setDocumentTab(edit);$(edit?'#edit-tab':'#preview-tab').focus();});
$('#document-editor').addEventListener('input',event=>{documentText=event.target.value;manualEdited=true;$('#edit-notice').textContent='수정 내용이 복사·다운로드에 반영됩니다';});
$('#copy-document').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(documentText);notify('프롬프트를 복사했습니다. 바이브코딩 도구에 붙여 넣어주세요.');}catch{setDocumentTab(true);$('#document-editor').focus();$('#document-editor').select();notify('Ctrl+C로 선택된 프롬프트를 복사해주세요.');}});
$('#download-document').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob(['\ufeff'+documentText],{type:'text/markdown;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=documentName.replace(/[\\/:*?"<>|\x00-\x1f]/g,'_')+'_초기프롬프트.md';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('초기 프롬프트를 다운로드합니다.');});
renderContextQuestion();
setStage(1);
