from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..database import Database
from ..engine import SimulationEngine
from ..enums import EquipmentStatus, HygieneStatus, OrderStatus, Severity
from .theme import STYLE
from .widgets import MetricCard, TemperatureChart


NAV_ITEMS = [
    ("总览", "dashboard"), ("订单与调度", "orders"), ("库存与批次", "inventory"),
    ("仓库与冷库", "warehouses"), ("车辆", "trucks"), ("叉车与卫生", "forklifts"),
    ("月台", "docks"), ("实时监控", "monitor"), ("异常中心", "events"),
    ("追溯与召回", "trace"), ("报表", "reports"), ("模拟控制", "simulation"),
]


class MainWindow(QMainWindow):
    def __init__(self, engine: SimulationEngine, database: Database):
        super().__init__()
        self.engine, self.database = engine, database
        self.setWindowTitle("ColdChain Simulator · 冷链物流模拟系统")
        self.resize(1480, 900)
        self.setMinimumSize(1120, 700)
        self.setStyleSheet(STYLE)
        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: list[QPushButton] = []
        self._build_ui()
        self.engine.tick_completed.connect(self.refresh_all)
        self.engine.event_created.connect(lambda _event: self.refresh_events())
        self.refresh_all()

    def _build_ui(self) -> None:
        root = QWidget(); self.setCentralWidget(root)
        main = QHBoxLayout(root); main.setContentsMargins(0, 0, 0, 0); main.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(205)
        side = QVBoxLayout(sidebar); side.setContentsMargins(10, 18, 10, 12)
        brand = QLabel("❄  COLDCHAIN\n    SIMULATOR")
        brand.setStyleSheet("font-size:16px;font-weight:800;color:#42dbb7;padding:4px 8px 15px;")
        side.addWidget(brand)
        for label, key in NAV_ITEMS:
            button = QPushButton(label); button.setObjectName("nav"); button.setCheckable(True)
            button.clicked.connect(lambda checked=False, k=key: self.show_page(k))
            side.addWidget(button); self.nav_buttons.append(button)
        side.addStretch()
        note = QLabel("教学仿真系统\n不构成食品安全判定")
        note.setProperty("muted", True); note.setWordWrap(True); side.addWidget(note)
        main.addWidget(sidebar)
        right = QVBoxLayout(); right.setContentsMargins(0, 0, 0, 0); right.setSpacing(0)
        topbar = QFrame(); topbar.setObjectName("topbar"); topbar.setFixedHeight(67)
        top = QHBoxLayout(topbar); top.setContentsMargins(22, 8, 22, 8)
        self.page_title = QLabel("运营总览"); self.page_title.setStyleSheet("font-size:20px;font-weight:700;")
        top.addWidget(self.page_title); top.addStretch()
        self.weather_label = QLabel(); self.weather_label.setProperty("muted", True); top.addWidget(self.weather_label)
        self.time_label = QLabel(); self.time_label.setStyleSheet("font-size:17px;font-weight:700;color:#fff;"); top.addWidget(self.time_label)
        self.speed_combo = QComboBox(); self.speed_combo.addItems([f"×{x}" for x in self.engine.SPEEDS]); self.speed_combo.setCurrentText("×10")
        self.speed_combo.currentTextChanged.connect(lambda value: self.engine.set_speed(int(value[1:])))
        top.addWidget(self.speed_combo)
        self.run_button = QPushButton("▶ 开始"); self.run_button.setProperty("primary", True); self.run_button.clicked.connect(self.toggle_running); top.addWidget(self.run_button)
        right.addWidget(topbar)
        self.stack = QStackedWidget(); right.addWidget(self.stack, 1)
        main.addLayout(right, 1)
        self._add_page("dashboard", self._dashboard_page())
        self._add_page("orders", self._orders_page())
        self._add_page("inventory", self._inventory_page())
        self._add_page("warehouses", self._warehouses_page())
        self._add_page("trucks", self._trucks_page())
        self._add_page("forklifts", self._forklifts_page())
        self._add_page("docks", self._docks_page())
        self._add_page("monitor", self._monitor_page())
        self._add_page("events", self._events_page())
        self._add_page("trace", self._trace_page())
        self._add_page("reports", self._reports_page())
        self._add_page("simulation", self._simulation_page())
        self.show_page("dashboard")

    def _add_page(self, key: str, widget: QWidget) -> None:
        wrapper = QScrollArea(); wrapper.setWidgetResizable(True); wrapper.setFrameShape(QFrame.NoFrame); wrapper.setWidget(widget)
        self.pages[key] = wrapper; self.stack.addWidget(wrapper)

    def _base_page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(22, 20, 22, 22); layout.setSpacing(14)
        heading = QLabel(title); heading.setStyleSheet("font-size:19px;font-weight:700;"); layout.addWidget(heading)
        sub = QLabel(subtitle); sub.setProperty("muted", True); sub.setWordWrap(True); layout.addWidget(sub)
        return page, layout

    def _table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers)); table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True); table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().hide(); table.horizontalHeader().setStretchLastSection(True); table.setMinimumHeight(260)
        return table

    def _dashboard_page(self) -> QWidget:
        page, layout = self._base_page("冷链运营态势", "统一模拟时间驱动的仓储、设备、运输与风险概览")
        grid = QGridLayout(); self.metric_cards = {}
        accents = ["#35d3ad", "#48a8ff", "#ffb84d", "#ff6577", "#9d84ff", "#40d6df", "#f09660", "#6bd578"]
        for index, title in enumerate(("准时率", "温度合规", "运输中", "温度异常", "卫生异常", "累计能耗", "当前成本", "平均品质")):
            card = MetricCard(title, accent=accents[index]); self.metric_cards[title] = card
            grid.addWidget(card, index//4, index%4)
        layout.addLayout(grid)
        lower = QHBoxLayout()
        panel = QFrame(); panel.setObjectName("panel"); pv = QVBoxLayout(panel); pv.addWidget(QLabel("仓库实时温度"))
        self.dashboard_chart = TemperatureChart(); pv.addWidget(self.dashboard_chart); lower.addWidget(panel, 2)
        panel2 = QFrame(); panel2.setObjectName("panel"); p2 = QVBoxLayout(panel2); p2.addWidget(QLabel("最新事件"))
        self.dashboard_events = self._table(["时间", "级别", "内容"]); self.dashboard_events.setMinimumHeight(220); p2.addWidget(self.dashboard_events); lower.addWidget(panel2, 2)
        layout.addLayout(lower); layout.addStretch(); return page

    def _orders_page(self) -> QWidget:
        page, layout = self._base_page("订单与调度中心", "车辆和叉车会基于容量、温区与卫生状态给出推荐；风险操作可强制执行并进入审计日志")
        self.order_table = self._table(["订单号", "状态", "路线", "批次", "车辆", "叉车", "截止时间", "利润"]); layout.addWidget(self.order_table)
        controls = QFrame(); controls.setObjectName("panel"); row = QHBoxLayout(controls)
        self.order_combo = QComboBox(); row.addWidget(QLabel("订单")); row.addWidget(self.order_combo)
        self.truck_combo = QComboBox(); row.addWidget(QLabel("车辆/舱")); row.addWidget(self.truck_combo)
        btn = QPushButton("分配车辆"); btn.clicked.connect(self.assign_selected_truck); row.addWidget(btn)
        btn = QPushButton("开始预冷"); btn.clicked.connect(self.precool_selected); row.addWidget(btn)
        self.forklift_combo = QComboBox(); row.addWidget(QLabel("叉车")); row.addWidget(self.forklift_combo)
        self.force_check = QCheckBox("强制执行"); row.addWidget(self.force_check)
        btn = QPushButton("开始履约"); btn.setProperty("primary", True); btn.clicked.connect(self.fulfill_selected); row.addWidget(btn)
        btn = QPushButton("到达后卸货"); btn.clicked.connect(self.unload_selected); row.addWidget(btn)
        layout.addWidget(controls)
        hint = QLabel("典型演示：为 CL202609010001 选择推荐 A02-C → 分配 → 预冷 → 运行至约 6℃ → 选择 F03 → 开始履约。选择 F01 会触发卫生拦截；勾选“强制执行”可观察污染风险与审计记录。")
        hint.setWordWrap(True); hint.setProperty("muted", True); layout.addWidget(hint); layout.addStretch(); return page

    def _inventory_page(self) -> QWidget:
        page, layout = self._base_page("库存与批次", "批次级温度、品质、效期、包装和污染风险；出库选择支持 FEFO")
        self.inventory_table = self._table(["批次", "SKU", "品名", "位置", "状态", "重量kg", "核心℃", "允许范围", "品质", "污染风险", "包装", "到期日"])
        layout.addWidget(self.inventory_table); return page

    def _warehouses_page(self) -> QWidget:
        page, layout = self._base_page("仓库与冷库", "库区空气温度由环境、门、制冷回差、除霜和供电共同决定；货物温度具有热惯性")
        self.zone_table = self._table(["仓库", "库区", "温度℃", "目标℃", "湿度", "货物批次", "制冷", "除霜", "供电"]); layout.addWidget(self.zone_table)
        row = QHBoxLayout(); self.power_warehouse = QComboBox(); self.power_warehouse.addItems(self.engine.warehouses.keys()); row.addWidget(self.power_warehouse)
        off = QPushButton("制造停电"); off.setProperty("danger", True); off.clicked.connect(lambda: self._act(lambda: self.engine.set_warehouse_power(self.power_warehouse.currentText(), False))); row.addWidget(off)
        on = QPushButton("启动/恢复电源"); on.clicked.connect(lambda: self._act(lambda: self.engine.set_warehouse_power(self.power_warehouse.currentText(), True))); row.addWidget(on); row.addStretch(); layout.addLayout(row); return page

    def _trucks_page(self) -> QWidget:
        page, layout = self._base_page("车辆与多温区车厢", "每个车厢独立记录空气温度、制冷、车门、容量、货物核心温度与运输进度")
        self.truck_table = self._table(["车辆", "类型", "状态", "车厢", "空气℃", "目标℃", "核心℃", "制冷", "车门", "位置/目的地", "剩余km", "能耗"]); layout.addWidget(self.truck_table)
        row = QHBoxLayout(); self.truck_action_combo = QComboBox(); row.addWidget(self.truck_action_combo)
        fault = QPushButton("制造制冷故障"); fault.setProperty("danger", True); fault.clicked.connect(self.inject_fault); row.addWidget(fault)
        repair = QPushButton("修复制冷"); repair.clicked.connect(self.repair_fault); row.addWidget(repair)
        traffic = QPushButton("制造 25 分钟拥堵"); traffic.clicked.connect(self.inject_traffic); row.addWidget(traffic)
        door = QPushButton("切换车门"); door.clicked.connect(self.toggle_door); row.addWidget(door); row.addStretch(); layout.addLayout(row); return page

    def _forklifts_page(self) -> QWidget:
        page, layout = self._base_page("叉车与卫生管理", "清洁负责去除污物，消毒进一步降低污染；有明显污物时不能跳过清洁")
        self.forklift_table = self._table(["叉车", "名称", "区域", "状态", "卫生", "污染物", "污染等级", "上一货类", "任务", "电量"]); layout.addWidget(self.forklift_table)
        row = QHBoxLayout(); self.forklift_action_combo = QComboBox(); self.forklift_action_combo.addItems(self.engine.forklifts.keys()); row.addWidget(self.forklift_action_combo)
        clean = QPushButton("开始清洁"); clean.clicked.connect(lambda: self._act(lambda: self.engine.clean_forklift(self.forklift_action_combo.currentText()))); row.addWidget(clean)
        disinfect = QPushButton("开始消毒"); disinfect.clicked.connect(lambda: self._act(lambda: self.engine.disinfect_forklift(self.forklift_action_combo.currentText()))); row.addWidget(disinfect); row.addStretch(); layout.addLayout(row); return page

    def _docks_page(self) -> QWidget:
        page, layout = self._base_page("月台调度", "车辆在月台不足时等待，装卸过程会打开库门与车门并造成热暴露")
        self.dock_table = self._table(["仓库", "月台", "占用车辆", "等待队列", "门状态"]); layout.addWidget(self.dock_table); return page

    def _monitor_page(self) -> QWidget:
        page, layout = self._base_page("实时温度监控", "蓝线为车厢/库区空气温度，橙线为货物核心温度；采样间隔由配置控制")
        row = QHBoxLayout(); row.addWidget(QLabel("监控对象")); self.monitor_combo = QComboBox(); self.monitor_combo.currentTextChanged.connect(self.refresh_monitor); row.addWidget(self.monitor_combo)
        bias = QPushButton("模拟 -5℃ 偏差"); bias.clicked.connect(lambda: self._act(lambda: self.engine.set_sensor_fault(self.monitor_combo.currentText(), "正常", -5))); row.addWidget(bias)
        stuck = QPushButton("模拟传感器卡死"); stuck.clicked.connect(lambda: self._act(lambda: self.engine.set_sensor_fault(self.monitor_combo.currentText(), "卡死", -2))); row.addWidget(stuck)
        normal = QPushButton("恢复传感器"); normal.clicked.connect(lambda: self._act(lambda: self.engine.set_sensor_fault(self.monitor_combo.currentText(), "正常", 0))); row.addWidget(normal); row.addStretch(); layout.addLayout(row)
        panel = QFrame(); panel.setObjectName("panel"); pv = QVBoxLayout(panel); self.monitor_chart = TemperatureChart(); pv.addWidget(self.monitor_chart); layout.addWidget(panel); return page

    def _events_page(self) -> QWidget:
        page, layout = self._base_page("异常与事件中心", "所有设备、温度、卫生、时效和人工强制事件按时间记录，严重事件优先关注")
        self.event_table = self._table(["时间", "严重度", "类别", "对象", "内容", "建议"]); layout.addWidget(self.event_table); return page

    def _trace_page(self) -> QWidget:
        page, layout = self._base_page("批次追溯与召回", "从批次定位当前位置、关联订单、温度暴露和包装/污染状态；召回不会自动删除库存")
        self.trace_table = self._table(["批次", "品名", "当前位置", "关联订单", "状态", "超温分钟", "暴露指数", "最终风险"]); layout.addWidget(self.trace_table)
        row = QHBoxLayout(); self.recall_combo = QComboBox(); self.recall_combo.addItems(self.engine.cargo.keys()); row.addWidget(self.recall_combo)
        recall = QPushButton("发起批次召回"); recall.setProperty("danger", True); recall.clicked.connect(lambda: self._act(lambda: self.engine.recall_batch(self.recall_combo.currentText(), "用户在追溯中心发起召回"))); row.addWidget(recall); row.addStretch(); layout.addLayout(row); return page

    def _reports_page(self) -> QWidget:
        page, layout = self._base_page("运营与订单报告", "生成 JSON 全链路摘要，事件日志可导出为 UTF-8 CSV")
        row = QHBoxLayout(); self.report_order_combo = QComboBox(); row.addWidget(self.report_order_combo)
        generate = QPushButton("生成订单报告"); generate.setProperty("primary", True); generate.clicked.connect(self.export_report); row.addWidget(generate)
        export = QPushButton("导出事件 CSV"); export.clicked.connect(self.export_events); row.addWidget(export); row.addStretch(); layout.addLayout(row)
        self.report_preview = QLabel("选择订单后生成报告"); self.report_preview.setTextInteractionFlags(Qt.TextSelectableByMouse); self.report_preview.setWordWrap(True); self.report_preview.setAlignment(Qt.AlignTop); self.report_preview.setStyleSheet("background:#151d29;border:1px solid #263447;padding:18px;"); self.report_preview.setMinimumHeight(420); layout.addWidget(self.report_preview); return page

    def _simulation_page(self) -> QWidget:
        page, layout = self._base_page("模拟控制与人工干预", "暂停后可调度、改变场景和处理异常；同一配置与随机种子可获得可重复结果")
        panel = QFrame(); panel.setObjectName("panel"); grid = QGridLayout(panel)
        grid.addWidget(QLabel("随机种子"),0,0); grid.addWidget(QLabel(str(self.engine.random_seed)),0,1)
        grid.addWidget(QLabel("模拟步长"),1,0); grid.addWidget(QLabel(f"{self.engine.tick_minutes} 分钟"),1,1)
        grid.addWidget(QLabel("温度采样"),2,0); grid.addWidget(QLabel(f"每 {self.engine.config['simulation']['sample_interval_minutes']} 分钟"),2,1)
        jump = QPushButton("单步 +1 分钟"); jump.clicked.connect(lambda: self.engine.advance(1)); grid.addWidget(jump,3,0)
        jump10 = QPushButton("推进 +10 分钟"); jump10.clicked.connect(lambda: self.engine.advance(10)); grid.addWidget(jump10,3,1)
        jump60 = QPushButton("推进 +60 分钟"); jump60.clicked.connect(lambda: self.engine.advance(60)); grid.addWidget(jump60,3,2)
        layout.addWidget(panel)
        warning = QLabel("模型边界：本软件使用一阶集总热模型、规则化品质损耗和企业 SOP 示例，适合教学、方案比较与流程演练，不自动代表符合任何国家标准，也不能替代微生物安全评估。")
        warning.setWordWrap(True); warning.setStyleSheet("color:#ffbe63;padding:14px;background:#2b2518;border:1px solid #665229;"); layout.addWidget(warning); layout.addStretch(); return page

    def show_page(self, key: str) -> None:
        self.stack.setCurrentWidget(self.pages[key]); titles = dict(NAV_ITEMS); self.page_title.setText(next(label for label,k in NAV_ITEMS if k==key))
        for button, (_, k) in zip(self.nav_buttons, NAV_ITEMS): button.setChecked(k == key)
        if key == "monitor": self.refresh_monitor()

    def toggle_running(self) -> None:
        self.engine.set_running(not self.engine.running)
        self.run_button.setText("Ⅱ 暂停" if self.engine.running else "▶ 开始")

    def _act(self, action) -> None:
        try:
            action(); self.refresh_all()
        except Exception as exc:
            QMessageBox.warning(self, "操作未完成", str(exc))

    def _selected_order(self) -> str:
        if not self.order_combo.currentText(): raise ValueError("没有可用订单")
        return self.order_combo.currentText()

    def assign_selected_truck(self) -> None:
        def action():
            oid = self._selected_order(); data = self.truck_combo.currentData()
            if not data: raise ValueError("请选择车辆")
            self.engine.assign_truck(oid, data[0], data[1], self.force_check.isChecked())
        self._act(action)

    def precool_selected(self) -> None: self._act(lambda: self.engine.start_precooling(self._selected_order()))
    def fulfill_selected(self) -> None:
        self._act(lambda: self.engine.begin_fulfillment(self._selected_order(), self.forklift_combo.currentData(), self.force_check.isChecked()))
    def unload_selected(self) -> None: self._act(lambda: self.engine.begin_unloading(self._selected_order()))

    def _truck_action(self):
        data = self.truck_action_combo.currentData()
        if not data: raise ValueError("请选择车厢")
        return data
    def inject_fault(self): self._act(lambda: self.engine.inject_refrigeration_fault(*self._truck_action()))
    def repair_fault(self): self._act(lambda: self.engine.repair_refrigeration(*self._truck_action()))
    def inject_traffic(self): self._act(lambda: self.engine.add_traffic_delay(self._truck_action()[0], 25))
    def toggle_door(self):
        def action():
            truck, comp = self._truck_action(); current = self.engine.trucks[truck].compartments[comp].door_open
            self.engine.set_door(truck, comp, not current)
        self._act(action)

    def export_report(self) -> None:
        oid = self.report_order_combo.currentText()
        if not oid: return
        reports = Path(__file__).resolve().parents[2] / "reports"; reports.mkdir(exist_ok=True)
        path = reports / f"{oid}_report.json"; self.engine.export_order_report(oid, path)
        data = self.engine.order_report(oid); self.report_preview.setText(json.dumps(data, ensure_ascii=False, indent=2))
        QMessageBox.information(self, "报告已生成", str(path))

    def export_events(self) -> None:
        reports = Path(__file__).resolve().parents[2] / "reports"; reports.mkdir(exist_ok=True)
        self.database.flush(); path = reports / "event_logs.csv"; self.database.export_events_csv(path)
        QMessageBox.information(self, "导出完成", str(path))

    @staticmethod
    def _fill(table: QTableWidget, rows: list[list[object]]) -> None:
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row): table.setItem(r, c, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def refresh_all(self) -> None:
        self.time_label.setText(self.engine.simulation_time.strftime("%Y-%m-%d  %H:%M"))
        self.weather_label.setText(f"{self.engine.weather}  {self.engine.environment_temperature:.1f}℃  湿度 {self.engine.humidity:.0f}%    ")
        for key, value in self.engine.kpis().items(): self.metric_cards[key].value.setText(value)
        self._refresh_orders(); self._refresh_inventory(); self._refresh_zones(); self._refresh_trucks(); self._refresh_forklifts(); self._refresh_docks(); self.refresh_events(); self._refresh_trace(); self._refresh_combos(); self.refresh_monitor()
        samples = [s for s in self.engine.samples if s.entity_id == "WYS-C"]
        self.dashboard_chart.set_data([s.air_temperature for s in samples], [None for _ in samples], "武夷山冷藏库 · 近 100 个采样")

    def _refresh_orders(self):
        rows=[]
        for o in self.engine.orders.values(): rows.append([o.order_id,o.status.value,f"{o.origin} → {o.destination}",", ".join(o.cargo_ids),o.truck_id or "—",o.forklift_id or "—",o.deadline.strftime("%m-%d %H:%M"),f"¥{o.profit:.0f}"])
        self._fill(self.order_table, rows)
    def _refresh_inventory(self):
        rows=[]
        for c in self.engine.cargo.values(): rows.append([c.batch_id,c.sku,c.name,c.location,c.status.value,f"{c.weight_kg:.0f}",f"{c.current_core_temperature:.1f}",f"{c.min_temperature:g}~{c.max_temperature:g}",f"{c.quality:.1f}",f"{c.contamination_risk:.0f}",c.package_integrity.value,c.expiry_date.strftime("%Y-%m-%d")])
        self._fill(self.inventory_table, rows)
    def _refresh_zones(self):
        rows=[]
        for w in self.engine.warehouses.values():
            for z in w.zones.values(): rows.append([w.name,z.name,f"{z.current_temperature:.1f}",f"{z.temperature_setpoint:.1f}",f"{z.humidity:.0f}%",len(z.cargo_ids),"故障" if z.refrigeration.fault else ("运行" if z.refrigeration.running else "待机"),f"{z.refrigeration.defrost_remaining} min" if z.refrigeration.defrost_remaining else "—","正常" if w.power_status else "停电"])
        self._fill(self.zone_table, rows)
    def _refresh_trucks(self):
        rows=[]
        for t in self.engine.trucks.values():
            for c in t.compartments.values():
                core=sum(self.engine.cargo[x].current_core_temperature for x in c.cargo_ids)/len(c.cargo_ids) if c.cargo_ids else None
                rows.append([t.truck_id,t.truck_type,t.status.value,c.name,f"{c.current_temperature:.1f}",f"{c.target_temperature:.1f}",f"{core:.1f}" if core is not None else "—","故障" if c.refrigeration.fault else ("运行" if c.refrigeration.running else "待机"),"开启" if c.door_open else "关闭",t.destination or t.location,f"{t.distance_remaining_km:.1f}",f"{t.energy_kwh:.1f} kWh"])
        self._fill(self.truck_table, rows)
    def _refresh_forklifts(self):
        rows=[]
        for f in self.engine.forklifts.values(): rows.append([f.forklift_id,f.name,f.current_zone,f.status.value,f.hygiene_status.value,f.contamination_type or "—",f"{f.contamination_level:.0f}",f.last_cargo_category.value if f.last_cargo_category else "—",f.task or "—",f"{f.battery_percent:.0f}%"])
        self._fill(self.forklift_table, rows)
    def _refresh_docks(self):
        rows=[]
        for w in self.engine.warehouses.values():
            for d in w.docks.values(): rows.append([w.name,d.name,d.occupied_by or "空闲",", ".join(d.queue) or "—","开启" if d.door_open else "关闭"])
        self._fill(self.dock_table, rows)
    def refresh_events(self):
        events=self.engine.events[:100]; self._fill(self.event_table, [[e.time.strftime("%m-%d %H:%M"),e.severity.value,e.category,e.entity_id,e.message,e.recommendation] for e in events])
        self._fill(self.dashboard_events, [[e.time.strftime("%H:%M"),e.severity.value,e.message] for e in events[:8]])
    def _refresh_trace(self):
        rows=[]
        for c in self.engine.cargo.values(): rows.append([c.batch_id,c.name,c.location,c.order_id or "—",c.status.value,f"{c.excursion_minutes:.0f}",f"{c.degree_minutes:.1f}","高" if c.contamination_risk>=50 or c.quality<70 else ("关注" if c.excursion_minutes or c.contamination_risk else "低")])
        self._fill(self.trace_table, rows)

    def _refresh_combos(self):
        current=self.order_combo.currentText(); ids=list(self.engine.orders)
        if [self.order_combo.itemText(i) for i in range(self.order_combo.count())] != ids:
            self.order_combo.clear(); self.order_combo.addItems(ids); self.report_order_combo.clear(); self.report_order_combo.addItems(ids)
        if current in ids: self.order_combo.setCurrentText(current)
        oid=self.order_combo.currentText()
        self.truck_combo.clear(); self.forklift_combo.clear()
        if oid:
            for tid,cid,score in self.engine.recommend_truck(oid): self.truck_combo.addItem(f"{tid}/{cid}  评分 {score:.0f}",(tid,cid))
            for fid,result in self.engine.recommend_forklift(oid): self.forklift_combo.addItem(f"{fid} · {result.value}",fid)
        items=[]
        for t in self.engine.trucks.values():
            for c in t.compartments.values(): items.append((f"{t.truck_id}/{c.compartment_id}",(t.truck_id,c.compartment_id)))
        current_data=self.truck_action_combo.currentData(); self.truck_action_combo.clear()
        for label,data in items: self.truck_action_combo.addItem(label,data)
        index=self.truck_action_combo.findData(current_data)
        if index>=0:self.truck_action_combo.setCurrentIndex(index)
        monitor_items=[z.zone_id for w in self.engine.warehouses.values() for z in w.zones.values()]+[c.compartment_id for t in self.engine.trucks.values() for c in t.compartments.values()]
        if self.monitor_combo.count()==0:self.monitor_combo.addItems(monitor_items)

    def refresh_monitor(self):
        if not hasattr(self,"monitor_combo"): return
        eid=self.monitor_combo.currentText()
        if not eid:return
        samples=[s for s in self.engine.samples if s.entity_id==eid]
        sensor = self.engine.sensors.get(f"S-{eid}")
        suffix = f" · 传感器 {sensor.fault_mode} / 偏差 {sensor.bias:+.1f}℃" if sensor else ""
        self.monitor_chart.set_data([s.air_temperature for s in samples],[s.cargo_temperature for s in samples],f"{eid} · 真实温度趋势{suffix}")

    def closeEvent(self, event) -> None:
        self.engine.set_running(False); self.database.close(); event.accept()
