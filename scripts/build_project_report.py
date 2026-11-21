"""Build the submission PDF from the reviewable Markdown report source."""
import argparse
import html
import re
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (KeepTogether, LongTable, Paragraph,
                                SimpleDocTemplate, Spacer)


ROOT = Path(__file__).resolve().parents[1]
WIDTH = letter[0] - 80


def rich(value):
    value = html.escape(value.strip())
    value = re.sub(r'\[([^]]+)\]\(([^)]+)\)', lambda m: f'{m.group(1)} <font color="#486078">({m.group(2)})</font>', value)
    value = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', value)
    value = re.sub(r'`([^`]+)`', r'<font face="Courier">\1</font>', value)
    return value


def architecture():
    drawing = Drawing(WIDTH, 216)
    labels = [
        (8, 163, 116, 40, 'TENANTS A / B', 'React dashboard'),
        (153, 163, 116, 40, 'TRUSTED API', 'auth + admission'),
        (299, 163, 222, 40, 'FIRECRACKER GUEST', 'Python / LangGraph source'),
        (8, 81, 116, 40, 'MOCK BROKER', 'scoped tool call'),
        (153, 81, 116, 40, 'SNAPSHOTS', 'VM state + disk'),
        (299, 81, 222, 40, 'GRADING', 'hard tests -> judge -> review'),
    ]
    for x, y, w, h, title, subtitle in labels:
        drawing.add(Rect(x, y, w, h, rx=4, ry=4, strokeColor=colors.HexColor('#526b82'),
                         fillColor=colors.HexColor('#f1f5f8'), strokeWidth=.8))
        drawing.add(String(x + 9, y + 24, title, fontName='Helvetica-Bold', fontSize=8,
                           fillColor=colors.HexColor('#233446')))
        drawing.add(String(x + 9, y + 10, subtitle, fontName='Helvetica', fontSize=8))
    for a, b, c, d in [(124,183,153,183),(269,183,299,183),(410,163,410,121),
                       (211,163,211,121),(153,170,124,121)]:
        drawing.add(Line(a,b,c,d,strokeColor=colors.HexColor('#526b82'),strokeWidth=1.4))
    drawing.add(String(8, 18, 'Trust boundary: learner code and output stay inside guest; host owns policy, broker, and grades.',
                       fontSize=8, fillColor=colors.HexColor('#425468')))
    return drawing


def chart():
    d = Drawing(WIDTH, 140)
    d.add(String(9, 127, 'Offered load', fontName='Helvetica-Bold', fontSize=8))
    d.add(String(87, 127, 'Median request latency (seconds)', fontName='Helvetica-Bold', fontSize=8))
    d.add(String(341, 127, 'Throughput (requests / s)', fontName='Helvetica-Bold', fontSize=8))
    values = [(1,30.09,.032),(2,30.405,.066),(4,35.535,.111)]
    for i, (load, latency, throughput) in enumerate(values):
        y = 98 - i * 36
        d.add(String(20,y+8,str(load),fontName='Helvetica-Bold',fontSize=10))
        d.add(Rect(87,y,latency / 40 * 205,21,fillColor=colors.HexColor('#466e91'),strokeColor=None))
        d.add(String(92 + latency / 40 * 205,y+8,f'{latency:.2f}',fontSize=8))
        d.add(Rect(341,y,throughput / .13 * 128,21,fillColor=colors.HexColor('#78a59b'),strokeColor=None))
        d.add(String(346 + throughput / .13 * 128,y+8,f'{throughput:.3f}',fontSize=8))
    return d


def table(lines, normal, small):
    rows = [[cell.strip() for cell in line.strip().strip('|').split('|')] for line in lines]
    rows = [rows[0]] + rows[2:]
    columns = len(rows[0])
    if columns == 5:
        widths = [60, 145, 130, 82, WIDTH - 417]
    elif columns == 4:
        widths = [50, 215, 105, WIDTH - 370] if rows[0][0] == 'Priority' else [142, 105, 110, WIDTH - 357]
    else:
        widths = [WIDTH / columns] * columns
    data = [[Paragraph(rich(cell), small) for cell in row] for row in rows]
    obj = LongTable(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    obj.setStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dfe9f0')),
                  ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f7f9fb')]),
                  ('GRID',(0,0),(-1,-1),.35,colors.HexColor('#cbd3da')),
                  ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                  ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
                  ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)])
    return obj


def build(source, output):
    styles = getSampleStyleSheet()
    title = ParagraphStyle('ReportTitle', parent=styles['Title'], fontName='Helvetica-Bold',
                           fontSize=19, leading=22, textColor=colors.HexColor('#172c3c'),
                           spaceAfter=9, alignment=TA_LEFT)
    h1 = ParagraphStyle('Section', parent=styles['Heading1'], fontName='Helvetica-Bold',
                        fontSize=12.5, leading=15, spaceBefore=15, spaceAfter=7,
                        textColor=colors.HexColor('#172c3c'), keepWithNext=False)
    h1_keep = ParagraphStyle('SectionKeep', parent=h1, keepWithNext=True)
    body = ParagraphStyle('Body', parent=styles['BodyText'], fontName='Helvetica',
                          fontSize=9.5, leading=12.1, spaceAfter=5)
    small = ParagraphStyle('Cell', parent=body, fontSize=8, leading=10.4, spaceAfter=0)
    caption = ParagraphStyle('Caption', parent=body, fontSize=8.7, leading=11,
                             textColor=colors.HexColor('#405568'), spaceBefore=3)
    story = []
    lines = source.read_text(encoding='utf-8').splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith('```'):
            kind = line[3:]
            index += 1
            while index < len(lines) and not lines[index].startswith('```'):
                index += 1
            index += 1
            if kind == 'chart':
                while index < len(lines) and not lines[index].strip():
                    index += 1
                if index < len(lines) and lines[index].startswith('Figure 1.'):
                    story.append(KeepTogether([chart(), Spacer(1,5),
                                               Paragraph(rich(lines[index]), caption)]))
                    index += 1
                else:
                    story.append(chart())
            else:
                story.append(architecture())
            story.append(Spacer(1,7))
            continue
        if line.startswith('|'):
            group = []
            while index < len(lines) and lines[index].startswith('|'):
                group.append(lines[index])
                index += 1
            story.append(table(group, body, small))
            story.append(Spacer(1,7))
            continue
        if line.startswith('# '):
            story.append(Paragraph(rich(line[2:]), title))
            index += 1
            continue
        if line.startswith('## '):
            story.append(Paragraph(rich(line[3:]), h1 if line.startswith('## 6.') else h1_keep))
            index += 1
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not lines[index].startswith(('#','|','```')):
            paragraph.append(lines[index].strip())
            index += 1
        content = ' '.join(paragraph)
        style = caption if content.startswith('Figure 1.') else body
        story.append(Paragraph(rich(content), style))
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output), pagesize=letter, rightMargin=40, leftMargin=40,
                            topMargin=39, bottomMargin=42, title='Secure Multi Tenant Agentic Workflow Sandbox Project Report',
                            author='Group 44')

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#c9d3db'))
        canvas.line(40, 32, letter[0]-40, 32)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#506478'))
        canvas.drawString(40, 20, 'Project V | Group 44 | CS5903')
        canvas.drawRightString(letter[0]-40, 20, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'docs/Project_Report.md')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/Project_Report.pdf')
    args = parser.parse_args()
    print(build(args.source, args.output))
