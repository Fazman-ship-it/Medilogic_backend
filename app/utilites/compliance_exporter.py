from io import BytesIO
from typing import List
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import matplotlib.pyplot as plt
from datetime import datetime

def generate_csv(summary_data: List[dict]) -> BytesIO:
    df = pd.DataFrame(summary_data)
    stream = BytesIO()
    df.to_csv(stream, index=False)
    stream.seek(0)
    return stream

def generate_pdf(summary_data: List[dict]) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Compliance Summary Report", styles['Title']), Spacer(1, 12)]

    if summary_data:
        headers = list(summary_data[0].keys())
        data = [headers] + [[str(row[key]) for key in headers] for row in summary_data]

        table = Table(data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")
        ]))

        elements.append(table)
    else:
        elements.append(Paragraph("No data available.", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer

def generate_compliance_chart(summary_data: List[dict]) -> BytesIO:
    compliant = sum(1 for item in summary_data if item["overall_compliant"])
    non_compliant = len(summary_data) - compliant

    fig, ax = plt.subplots()
    ax.pie([compliant, non_compliant], labels=["Compliant", "Non-Compliant"], autopct="%1.1f%%")
    ax.set_title("Compliance Overview")

    img_buffer = BytesIO()
    plt.savefig(img_buffer, format="png")
    plt.close(fig)
    img_buffer.seek(0)
    return img_buffer