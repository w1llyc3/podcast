"""Free offline, extractive study notes. Never presents generated claims as facts."""
import re

def build_notes(title, paragraphs, segments):
    lines=[f'# {title}', '', '模式：本地原文摘录；未经人工校对，不是生成式深度总结。金融数字、专名及引文须对照音频。', '']
    buckets=[('核心观点摘录',r'核心|本质|不是|而是|我认为|我觉得|首先'),('论据和例子',r'例如|比如|因为|所以|数据|20\d\d|\d+[%％亿万]'),('反方与边界',r'但是|然而|风险|如果|不一定|并不|不是所有'),('自述交易线索（待核验）',r'我买|我卖|我持有|我们买|我们持有'),('建议或假设线索（待核验）',r'建议|假如|假设|如果')]
    for heading,pattern in buckets:
        matches=[(i+1,p) for i,p in enumerate(paragraphs) if re.search(pattern,p)][:3]
        lines.extend([f'## {heading}', ''])
        if matches:
            for i,p in matches:lines.extend([f'> {p}',f'来源：transcript.txt 第 {i} 段。',''])
        else:lines.extend(['未从转录中可靠提取；不推断。',''])
    tokens=sorted(set(re.findall(r'\b[A-Z]{2,6}\b', ''.join(paragraphs))))
    lines.extend(['## 资产与代码','', '仅发现大写候选词（未确认为股票代码）：'+('、'.join(tokens) if tokens else '无可靠候选')+'。', '', '## 学习与核验清单','', '- 核验原文中每一处金额、百分比、年份、人物及机构名称。','- 核心观点的成立条件是什么？原文举例能否充分支持？','- 哪些证据会使原观点失效？原文没有回答时保持未决。','- 交易自述、建议与假设仅给线索，不代替语境核查。','- 跨期观点变化：未建立可靠历史对照，本次不推断。',''])
    suspect=[i+1 for i,s in enumerate(segments) if s.get('avg_logprob',0)<-.8 or s.get('no_speech_prob',0)>.5]
    lines.extend(['识别置信度较低的原始分段序号：'+(', '.join(map(str,suspect)) if suspect else '未触发阈值；这不代表文字无误')+'。',''])
    return '\n'.join(lines)
