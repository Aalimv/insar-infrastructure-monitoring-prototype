
import streamlit as st
import pandas as pd
import plotly.express as px
import streamlit as st
import pandas as pd
import plotly.express as px

from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)

st.set_page_config(
    page_title="InSAR Infrastructure Intelligence",
    page_icon="🛰️",
    layout="wide"
)

st.title("🛰️ Infrastructure Intelligence Platform")
st.caption("Satellite-derived Ground Movement Monitoring")

st.sidebar.header("Data Management")

uploaded_file = st.sidebar.file_uploader(
    "Upload displacement CSV",
    type=["csv"]
)

st.divider()

if uploaded_file is None:
    st.info("Upload a CSV file to begin monitoring.")

    st.subheader("Required CSV Format")

    example = pd.DataFrame({
        "point_id": ["P001", "P001", "P002"],
        "latitude": [11.685, 11.685, 11.690],
        "longitude": [76.130, 76.130, 76.140],
        "date": ["2026-01-01", "2026-02-01", "2026-02-01"],
        "displacement_mm": [0.0, -3.2, 1.5]
    })

    st.dataframe(example, width="stretch")

else:
    try:
        df = pd.read_csv(uploaded_file)

        required = [
            "point_id",
            "latitude",
            "longitude",
            "date",
            "displacement_mm"
        ]

        missing = [col for col in required if col not in df.columns]

        if missing:
            st.error(f"Missing columns: {', '.join(missing)}")
            st.stop()

        df["date"] = pd.to_datetime(df["date"], errors="coerce")

        for col in ["latitude", "longitude", "displacement_mm"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=required)

        if df.empty:
            st.error("No valid measurement records found.")
            st.stop()

        if not df["latitude"].between(-90, 90).all():
            st.error("Invalid latitude values.")
            st.stop()

        if not df["longitude"].between(-180, 180).all():
            st.error("Invalid longitude values.")
            st.stop()

        st.success("CSV successfully loaded and validated.")

        col1, col2, col3 = st.columns(3)

        col1.metric("Measurement Records", len(df))
        col2.metric("Monitoring Points", df["point_id"].nunique())
        col3.metric(
            "Latest Measurement",
            df["date"].max().strftime("%d %b %Y")
        )

        st.subheader("Displacement Measurements")
        st.dataframe(df, width="stretch")

        st.subheader("Monitoring Location Map")

        locations = df[["latitude", "longitude"]].drop_duplicates()

        st.map(locations)

        st.subheader("Ground Movement Time Series")

        selected_point = st.selectbox(
            "Select Monitoring Point",
            sorted(df["point_id"].unique())
        )

        point_data = df[df["point_id"] == selected_point]
        point_data = point_data.sort_values("date")

        fig = px.line(
            point_data,
            x="date",
            y="displacement_mm",
            markers=True,
            title=f"Displacement History: {selected_point}",
            labels={
                "date": "Date",
                "displacement_mm": "Displacement (mm)"
            }
        )

        st.plotly_chart(fig, width="stretch")
	
        st.divider()

        st.header("🚨 Ground Movement Anomaly Screening")

        st.caption(
            "Rule-based screening for investigation prioritisation. "
            "Not a landslide prediction or safety classification."
        )

        col1, col2 = st.columns(2)

        with col1:
            displacement_limit = st.slider(
                "Absolute displacement threshold (mm)",
                min_value=1.0,
                max_value=50.0,
                value=10.0,
                step=1.0
            )

        with col2:
            rate_limit = st.slider(
                "Displacement rate threshold (mm/month)",
                min_value=0.5,
                max_value=20.0,
                value=5.0,
                step=0.5
            )

        # Calculate the absolute displacement
        # and rate between consecutive observations.
        df_screen = df.sort_values(
            ["point_id", "date"]
        ).copy()

        df_screen["change_mm"] = (
            df_screen.groupby("point_id")["displacement_mm"].diff()
        )

        df_screen["days_between"] = (
            df_screen.groupby("point_id")["date"]
            .diff()
            .dt.total_seconds() / 86400
        )

        df_screen["rate_mm_per_month"] = (
            df_screen["change_mm"].abs()
            / df_screen["days_between"]
            * 30.4375
        )

        summary = (
            df_screen.groupby("point_id")
            .agg(
                max_abs_displacement_mm=(
                    "displacement_mm",
                    lambda x: x.abs().max()
                ),
                max_rate_mm_per_month=(
                    "rate_mm_per_month",
                    "max"
                )
            )
            .reset_index()
        )

        summary["absolute_flag"] = (
            summary["max_abs_displacement_mm"]
            >= displacement_limit
        )

        summary["rate_flag"] = (
            summary["max_rate_mm_per_month"]
            >= rate_limit
        )

        summary["investigation_status"] = summary.apply(
            lambda row:
                "Investigate" if (
                    row["absolute_flag"] or row["rate_flag"]
                ) else "No threshold exceeded",
            axis=1
        )

        summary["flag_reason"] = summary.apply(
            lambda row: ", ".join(
                reason for condition, reason in [
                    (row["absolute_flag"], "Absolute displacement"),
                    (row["rate_flag"], "Displacement rate")
                ] if condition
            ) or "None",
            axis=1
        )

        flagged = summary[
            summary["investigation_status"] == "Investigate"
        ]

        col1, col2, col3 = st.columns(3)

        col1.metric("Points Analysed", len(summary))
        col2.metric("Points Flagged", len(flagged))
        col3.metric(
            "Points Not Flagged",
            len(summary) - len(flagged)
        )

        if len(flagged) > 0:
            st.warning(
                "Some monitoring points exceeded the selected "
                "screening thresholds. Further investigation is recommended."
            )
        else:
            st.success(
                "No monitoring points exceeded the selected thresholds."
            )

        st.subheader("Investigation Screening Results")

        st.dataframe(
            summary,
            width="stretch",
            hide_index=True
        )

        st.caption(
            "Rate is calculated from the absolute change between "
            "consecutive observations, normalised to a 30.4375-day month. "
            "Results depend on data quality, observation intervals and "
            "user-selected thresholds."
        )
	
        st.divider()
        st.header("PDF Monitoring Report")

        def create_pdf_report(summary, df):
            buffer = BytesIO()

            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4
            )

            styles = getSampleStyleSheet()
            story = []

            story.append(Paragraph(
                "InSAR Infrastructure Monitoring Report",
                styles["Title"]
            ))

            story.append(Spacer(1, 15))

            story.append(Paragraph(
                f"Generated: {datetime.now().strftime('%d %B %Y')}",
                styles["Normal"]
            ))

            story.append(Spacer(1, 15))

            story.append(Paragraph(
                "Monitoring Summary",
                styles["Heading2"]
            ))

            report_data = [
                ["Metric", "Value"],
                ["Measurement records", str(len(df))],
                ["Monitoring points", str(df["point_id"].nunique())],
                ["Flagged points", str(
                    (summary["investigation_status"] == "Investigate").sum()
                )],
                ["Latest observation", str(df["date"].max().date())]
            ]

            table = Table(report_data, colWidths=[250, 200])

            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("PADDING", (0, 0), (-1, -1), 8)
            ]))

            story.append(table)
            story.append(Spacer(1, 20))

            story.append(Paragraph(
                "Screening Results",
                styles["Heading2"]
            ))

            result_data = [
                ["Point", "Max displacement (mm)", "Status", "Reason"]
            ]

            for _, row in summary.iterrows():
                result_data.append([
                    str(row["point_id"]),
                    f'{row["max_abs_displacement_mm"]:.2f}',
                    str(row["investigation_status"]),
                    str(row["flag_reason"])
                ])

            result_table = Table(
                result_data,
                repeatRows=1,
                colWidths=[65, 140, 100, 145]
            )

            result_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("PADDING", (0, 0), (-1, -1), 7)
            ]))

            story.append(result_table)
            story.append(Spacer(1, 20))

            story.append(Paragraph(
                "Limitations",
                styles["Heading2"]
            ))

            story.append(Paragraph(
                "This report uses uploaded displacement measurements "
                "and preliminary rule-based screening. It is not a "
                "validated landslide prediction or structural safety "
                "assessment. Independent ground validation and "
                "InSAR quality assessment are required.",
                styles["BodyText"]
            ))

            doc.build(story)
            buffer.seek(0)

            return buffer.getvalue()

        pdf_data = create_pdf_report(summary, df)

        st.download_button(
            label="Download PDF Monitoring Report",
            data=pdf_data,
            file_name="InSAR_Monitoring_Report.pdf",
            mime="application/pdf",
            width="stretch"
        )



        st.caption(
            "Demo/research interface. Displacement measurements require "
            "InSAR quality screening and independent ground validation "
            "before operational decisions."
        )

    except Exception as e:
        st.error(f"Unable to process CSV: {e}")
