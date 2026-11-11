"""Moving the follow-ups out of comments written before they had a box of their own: the charts
where one was found, each shown split, for the user to tick the ones to move."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..db import RecordStore
from ..followup import FollowupSplit, followup_splits
from .i18n import tr


class FollowupReviewDialog(QDialog):
    """Applying writes the ticked charts' split texts in one transaction. Either way the review
    is marked done, so it is not offered again at the next start."""

    def __init__(self, store: RecordStore, splits: list[FollowupSplit], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.splits = {s.record.id: s for s in splits}
        self.setWindowTitle(tr("拆分 Follow-up"))
        self.resize(900, 600)
        intro = QLabel(tr("這些舊病歷的記錄裡找到 follow-up。勾選要把它移到「追蹤」的病歷，"
                          "點一筆可以看拆分後的樣子。"))
        intro.setWordWrap(True)
        self.items = QListWidget()
        names = {s.id: s.name for s in store.students()}
        for split in splits:
            item = QListWidgetItem(f"{names.get(split.record.student_id, '')} · {split.record.visit_date.isoformat()}")
            item.setData(Qt.ItemDataRole.UserRole, split.record.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.items.addItem(item)
        self.boxes = {key: self._read_only() for key in ("zh_text", "zh_followup", "en_text", "en_followup")}
        preview = QGridLayout()
        preview.addWidget(QLabel(tr("記錄")), 0, 1)
        preview.addWidget(QLabel(tr("追蹤")), 0, 2)
        for row, (language, prefix) in enumerate(((tr("中文"), "zh"), ("English", "en")), start=1):
            preview.addWidget(QLabel(language), row, 0, Qt.AlignmentFlag.AlignTop)
            preview.addWidget(self.boxes[f"{prefix}_text"], row, 1)
            preview.addWidget(self.boxes[f"{prefix}_followup"], row, 2)
        buttons = QDialogButtonBox()
        self.apply_btn = buttons.addButton(tr("套用"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(tr("都不要搬"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.apply)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.items, 1)
        layout.addLayout(preview, 2)
        layout.addWidget(buttons)
        self.items.currentItemChanged.connect(lambda item, _: self.show_split(item))
        self.items.setCurrentRow(0)
        self.finished.connect(lambda _: store.set_followups_reviewed())

    @staticmethod
    def _read_only() -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setReadOnly(True)
        return box

    def show_split(self, item: QListWidgetItem | None) -> None:
        texts = self.splits[item.data(Qt.ItemDataRole.UserRole)].texts() if item else {}
        for key, box in self.boxes.items():
            box.setPlainText(texts.get(key, ""))

    def checked_ids(self) -> list[int]:
        return [self.items.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.items.count())
                if self.items.item(i).checkState() == Qt.CheckState.Checked]

    def apply(self) -> None:
        self.store.set_chart_texts({record_id: self.splits[record_id].texts() for record_id in self.checked_ids()})
        self.accept()


def offer_followup_review(store: RecordStore, parent: QWidget | None = None, again: bool = False) -> bool:
    """Show the review if there is anything to move and it was not done before (or `again`).
    Reads every chart's comments, so it runs once, after unlocking. Returns whether it was
    shown; with nothing found, the review is marked done without asking."""
    if store.followups_reviewed() and not again:
        return False
    splits = followup_splits(store.records_between(date.min, date.max))
    if not splits:
        store.set_followups_reviewed()
        return False
    FollowupReviewDialog(store, splits, parent).exec()
    return True
