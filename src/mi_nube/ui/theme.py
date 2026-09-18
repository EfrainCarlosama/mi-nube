APPLICATION_STYLE = """
QWidget {
    color: #172033;
    font-family: "Segoe UI";
    font-size: 14px;
}
QMainWindow, QWidget#AppRoot {
    background: #F4F7FB;
}
QFrame#Sidebar {
    background: #111827;
    border: none;
}
QLabel#BrandMark {
    background: #4F7DF3;
    border-radius: 10px;
    color: white;
    font-size: 18px;
    font-weight: 700;
}
QLabel#BrandName {
    color: white;
    font-size: 19px;
    font-weight: 700;
}
QLabel#BrandCaption, QLabel#SidebarCaption {
    color: #8E9AAF;
    font-size: 11px;
}
QPushButton[nav="true"] {
    background: transparent;
    border: none;
    border-radius: 9px;
    color: #AEB8C9;
    font-size: 14px;
    padding: 10px 13px;
    text-align: left;
}
QPushButton[nav="true"]:hover {
    background: #1C2638;
    color: white;
}
QPushButton[nav="true"]:checked {
    background: #26344D;
    color: white;
    font-weight: 600;
}
QFrame#TopBar {
    background: white;
    border-bottom: 1px solid #E7EBF2;
}
QLineEdit#SearchInput {
    background: #F3F5F9;
    border: 1px solid #E6EAF0;
    border-radius: 10px;
    padding: 9px 14px;
    selection-background-color: #4F7DF3;
}
QLineEdit#SearchInput:focus {
    border: 1px solid #4F7DF3;
    background: white;
}
QPushButton[primary="true"] {
    background: #4F7DF3;
    border: none;
    border-radius: 9px;
    color: white;
    font-weight: 600;
    padding: 10px 16px;
}
QPushButton[primary="true"]:hover { background: #3D6CE0; }
QPushButton[secondary="true"] {
    background: white;
    border: 1px solid #DCE2EB;
    border-radius: 9px;
    color: #364158;
    padding: 9px 14px;
}
QPushButton[secondary="true"]:hover { background: #F6F8FB; }
QPushButton[danger="true"] {
    background: #FFF5F5;
    border: 1px solid #F4C7C7;
    border-radius: 9px;
    color: #B42318;
    font-weight: 600;
    padding: 9px 14px;
}
QPushButton[danger="true"]:hover { background: #FEECEC; }
QPushButton:disabled {
    background: #E8ECF2;
    border-color: #E0E4EA;
    color: #98A2B3;
}
QLabel#PageTitle {
    color: #101828;
    font-size: 26px;
    font-weight: 700;
}
QLabel#PageSubtitle { color: #667085; font-size: 13px; }
QLabel#SectionTitle { color: #1D2939; font-size: 17px; font-weight: 650; }
QLabel#Muted { color: #7B879B; font-size: 12px; }
QLabel#Metric { color: #101828; font-size: 25px; font-weight: 700; }
QLabel#AccountAvatar {
    background: #E8EFFF;
    border-radius: 24px;
    color: #315DC5;
    font-size: 17px;
    font-weight: 700;
}
QLabel[success="true"] { color: #087A5A; font-weight: 600; }
QLabel[warning="true"] { color: #B54708; font-weight: 600; }
QFrame[card="true"] {
    background: white;
    border: 1px solid #E6EAF0;
    border-radius: 13px;
}
QProgressBar {
    background: #E8EDF5;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}
QProgressBar::chunk { background: #4F7DF3; border-radius: 4px; }
QTableWidget {
    background: white;
    alternate-background-color: #FAFBFD;
    border: 1px solid #E6EAF0;
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: #E8EFFF;
    selection-color: #172033;
}
QHeaderView::section {
    background: #F8FAFC;
    border: none;
    border-bottom: 1px solid #E6EAF0;
    color: #667085;
    font-size: 12px;
    font-weight: 600;
    padding: 10px;
}
QScrollArea { border: none; background: transparent; }
QStackedWidget { background: #F4F7FB; }
"""
