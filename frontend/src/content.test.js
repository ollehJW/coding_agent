import test from 'node:test';
import assert from 'node:assert/strict';
import { answerText, answerBasis } from './content.js';
const questions = [
 {id:'q1',topic:'data_model',title:'어떤 엑셀 항목을 합치나요?'},
 {id:'q2',topic:'data_model',title:'열 순서가 다르면 어떻게 찾나요?'},
 {id:'q3',topic:'environment',title:'어디에서 사용하나요?'},
];
test('선택 답변과 직접 입력을 합치고 빈 답변을 판별한다',()=>{
 assert.equal(answerText({selected:['현황','중복 방지'],custom:' 메모 '}),['현황','중복 방지','메모'].join(String.fromCharCode(10)));
 assert.equal(answerText({selected:[],custom:'  '}),'');
 assert.equal(answerText(undefined),'');
});
test('답변 기준은 백엔드와 같은 형식으로 앞선 답변만 반영한다',()=>{
 const answers={q1:{selected:['생산량'],custom:'"따옴표"'},q2:{selected:['열 제목'],custom:''}};
 assert.equal(answerBasis(questions,answers,0),'[]');
 assert.equal(answerBasis(questions,answers,1),'[[["생산량"],"\\"따옴표\\""]]');
});
