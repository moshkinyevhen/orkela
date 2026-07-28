#include "orkela/localization.h"

#include <array>
#include <cctype>
#include <string>

namespace orkela {
namespace {

constexpr std::size_t text_count =
    static_cast<std::size_t>(text_id::count);
using text_table = std::array<std::string_view, text_count>;

constexpr text_table english = {
    "Orkela",
    "Truth-first listening",
    "LOCAL • PRIVATE",
    "NOW PLAYING",
    "Native Resonith",
    "C++23 portable session",
    "RESONITH",
    "CAUSAL FIELD",
    "Decoded truth • live PCM field",
    "Change the analytical view in Visual settings",
    "Ready • direct native pull decode",
    "Playing",
    "Paused",
    "Playback complete",
    "Stopped",
    "Authenticating Resonith stream…",
    "Seeking",
    "LISTENING",
    "Volume",
    "Repeat off",
    "Repeat on",
    "SOURCE",
    "Open Resonith",
    "Load demo",
    "Settings",
    "Interface",
    "Language",
    "Follow the system language or select an interface language.",
    "System default",
    "Done",
    "Field",
    "Spectrum",
    "Wave",
    "History",
    "Local playback • no telemetry",
    "Direct .resonith playback • offline by design",
    "Playback failed",
    "Overview",
    "Playback",
    "Audio",
    "Visuals",
    "Video",
    "Subtitles",
    "Library",
    "Performance",
    "Privacy",
    "Hotkeys",
    "Advanced",
    "Command Center",
    "Play",
    "Pause",
    "Resume",
    "Stop",
    "Back 10 seconds",
    "Forward 10 seconds",
    "Playback timeline",
    "Playback information",
};

constexpr text_table german = {
    "Orkela",
    "Originalgetreues Hören",
    "LOKAL • PRIVAT",
    "AKTUELLE WIEDERGABE",
    "Natives Resonith",
    "Portable C++23-Sitzung",
    "RESONITH",
    "KAUSALFELD",
    "Dekodiertes Original • Live-PCM-Feld",
    "Analyseansicht in den Visual-Einstellungen ändern",
    "Bereit • direkte native Dekodierung",
    "Wiedergabe",
    "Pausiert",
    "Wiedergabe beendet",
    "Gestoppt",
    "Resonith-Stream wird geprüft…",
    "Suche",
    "WIEDERGABE",
    "Lautstärke",
    "Wiederholen aus",
    "Wiederholen an",
    "QUELLE",
    "Resonith öffnen",
    "Demo laden",
    "Einstellungen",
    "Oberfläche",
    "Sprache",
    "Systemsprache verwenden oder eine Oberflächensprache wählen.",
    "Systemstandard",
    "Fertig",
    "Feld",
    "Spektrum",
    "Welle",
    "Verlauf",
    "Lokale Wiedergabe • keine Telemetrie",
    "Direkte .resonith-Wiedergabe • offline entwickelt",
    "Wiedergabe fehlgeschlagen",
    "Übersicht",
    "Wiedergabe",
    "Audio",
    "Visualisierung",
    "Video",
    "Untertitel",
    "Mediathek",
    "Leistung",
    "Datenschutz",
    "Tastenkürzel",
    "Erweitert",
    "Kontrollzentrum",
    "Wiedergabe",
    "Pause",
    "Fortsetzen",
    "Stopp",
    "10 Sekunden zurück",
    "10 Sekunden vor",
    "Wiedergabe-Zeitleiste",
    "Wiedergabeinformationen",
};

constexpr text_table spanish = {
    "Orkela",
    "Escucha fiel al original",
    "LOCAL • PRIVADO",
    "REPRODUCIENDO",
    "Resonith nativo",
    "Sesión portátil C++23",
    "RESONITH",
    "CAMPO CAUSAL",
    "Original decodificado • campo PCM en vivo",
    "Cambia la vista analítica en los ajustes visuales",
    "Listo • decodificación nativa directa",
    "Reproduciendo",
    "En pausa",
    "Reproducción finalizada",
    "Detenido",
    "Verificando el flujo Resonith…",
    "Buscando",
    "ESCUCHA",
    "Volumen",
    "Repetición desactivada",
    "Repetición activada",
    "FUENTE",
    "Abrir Resonith",
    "Cargar demo",
    "Ajustes",
    "Interfaz",
    "Idioma",
    "Usa el idioma del sistema o elige el idioma de la interfaz.",
    "Predeterminado del sistema",
    "Listo",
    "Campo",
    "Espectro",
    "Onda",
    "Historial",
    "Reproducción local • sin telemetría",
    "Reproducción .resonith directa • diseñada sin conexión",
    "Error de reproducción",
    "Resumen",
    "Reproducción",
    "Audio",
    "Visuales",
    "Vídeo",
    "Subtítulos",
    "Biblioteca",
    "Rendimiento",
    "Privacidad",
    "Atajos",
    "Avanzado",
    "Centro de control",
    "Reproducir",
    "Pausa",
    "Reanudar",
    "Detener",
    "Retroceder 10 segundos",
    "Avanzar 10 segundos",
    "Línea de tiempo de reproducción",
    "Información de reproducción",
};

constexpr text_table italian = {
    "Orkela",
    "Ascolto fedele all’originale",
    "LOCALE • PRIVATO",
    "IN RIPRODUZIONE",
    "Resonith nativo",
    "Sessione portabile C++23",
    "RESONITH",
    "CAMPO CAUSALE",
    "Originale decodificato • campo PCM dal vivo",
    "Cambia la vista analitica nelle impostazioni visive",
    "Pronto • decodifica nativa diretta",
    "In riproduzione",
    "In pausa",
    "Riproduzione completata",
    "Arrestato",
    "Verifica del flusso Resonith…",
    "Ricerca",
    "ASCOLTO",
    "Volume",
    "Ripetizione disattivata",
    "Ripetizione attivata",
    "SORGENTE",
    "Apri Resonith",
    "Carica demo",
    "Impostazioni",
    "Interfaccia",
    "Lingua",
    "Usa la lingua di sistema o scegli la lingua dell’interfaccia.",
    "Predefinita di sistema",
    "Fine",
    "Campo",
    "Spettro",
    "Onda",
    "Cronologia",
    "Riproduzione locale • nessuna telemetria",
    "Riproduzione .resonith diretta • progettata offline",
    "Riproduzione non riuscita",
    "Panoramica",
    "Riproduzione",
    "Audio",
    "Visualizzazioni",
    "Video",
    "Sottotitoli",
    "Libreria",
    "Prestazioni",
    "Privacy",
    "Scorciatoie",
    "Avanzate",
    "Centro di controllo",
    "Riproduci",
    "Pausa",
    "Riprendi",
    "Stop",
    "Indietro di 10 secondi",
    "Avanti di 10 secondi",
    "Sequenza temporale di riproduzione",
    "Informazioni sulla riproduzione",
};

constexpr text_table japanese = {
    "Orkela",
    "原音を忠実に再生",
    "ローカル • プライベート",
    "再生中",
    "ネイティブ Resonith",
    "C++23 ポータブルセッション",
    "RESONITH",
    "因果フィールド",
    "復号された原音 • ライブ PCM フィールド",
    "ビジュアル設定で解析表示を変更",
    "準備完了 • ネイティブ直接デコード",
    "再生中",
    "一時停止",
    "再生完了",
    "停止",
    "Resonith ストリームを検証中…",
    "シーク中",
    "リスニング",
    "音量",
    "リピート オフ",
    "リピート オン",
    "ソース",
    "Resonith を開く",
    "デモを読み込む",
    "設定",
    "インターフェース",
    "言語",
    "システム言語を使うか、表示言語を選択します。",
    "システム設定",
    "完了",
    "フィールド",
    "スペクトラム",
    "波形",
    "履歴",
    "ローカル再生 • テレメトリなし",
    ".resonith を直接再生 • オフライン設計",
    "再生に失敗しました",
    "概要",
    "再生",
    "オーディオ",
    "ビジュアル",
    "ビデオ",
    "字幕",
    "ライブラリ",
    "パフォーマンス",
    "プライバシー",
    "ショートカット",
    "詳細",
    "コマンドセンター",
    "再生",
    "一時停止",
    "再開",
    "停止",
    "10秒戻る",
    "10秒進む",
    "再生タイムライン",
    "再生情報",
};

constexpr text_table korean = {
    "Orkela",
    "원음 우선 감상",
    "로컬 • 비공개",
    "지금 재생 중",
    "네이티브 Resonith",
    "C++23 이식형 세션",
    "RESONITH",
    "인과 필드",
    "디코딩된 원음 • 실시간 PCM 필드",
    "시각 설정에서 분석 화면을 변경하세요",
    "준비됨 • 네이티브 직접 디코딩",
    "재생 중",
    "일시 정지",
    "재생 완료",
    "정지됨",
    "Resonith 스트림 확인 중…",
    "탐색 중",
    "감상",
    "볼륨",
    "반복 끔",
    "반복 켬",
    "소스",
    "Resonith 열기",
    "데모 불러오기",
    "설정",
    "인터페이스",
    "언어",
    "시스템 언어를 따르거나 인터페이스 언어를 선택합니다.",
    "시스템 기본값",
    "완료",
    "필드",
    "스펙트럼",
    "파형",
    "기록",
    "로컬 재생 • 원격 측정 없음",
    ".resonith 직접 재생 • 오프라인 설계",
    "재생 실패",
    "개요",
    "재생",
    "오디오",
    "시각화",
    "비디오",
    "자막",
    "라이브러리",
    "성능",
    "개인정보",
    "단축키",
    "고급",
    "명령 센터",
    "재생",
    "일시 정지",
    "계속",
    "정지",
    "10초 뒤로",
    "10초 앞으로",
    "재생 타임라인",
    "재생 정보",
};

constexpr text_table chinese_simplified = {
    "Orkela",
    "忠于原声的聆听",
    "本地 • 私密",
    "正在播放",
    "原生 Resonith",
    "C++23 可移植会话",
    "RESONITH",
    "因果场",
    "解码原声 • 实时 PCM 场",
    "在可视化设置中切换分析视图",
    "就绪 • 原生直接解码",
    "正在播放",
    "已暂停",
    "播放完成",
    "已停止",
    "正在验证 Resonith 流…",
    "正在跳转",
    "聆听",
    "音量",
    "关闭重复",
    "开启重复",
    "来源",
    "打开 Resonith",
    "加载演示",
    "设置",
    "界面",
    "语言",
    "跟随系统语言或选择界面语言。",
    "系统默认",
    "完成",
    "声场",
    "频谱",
    "波形",
    "历史",
    "本地播放 • 无遥测",
    "直接播放 .resonith • 离线设计",
    "播放失败",
    "概览",
    "播放",
    "音频",
    "可视化",
    "视频",
    "字幕",
    "媒体库",
    "性能",
    "隐私",
    "快捷键",
    "高级",
    "控制中心",
    "播放",
    "暂停",
    "继续",
    "停止",
    "后退 10 秒",
    "前进 10 秒",
    "播放时间轴",
    "播放信息",
};

constexpr text_table russian = {
    "Orkela",
    "Прослушивание без подмены",
    "ЛОКАЛЬНО • ПРИВАТНО",
    "СЕЙЧАС ИГРАЕТ",
    "Нативный Resonith",
    "Переносимая сессия C++23",
    "RESONITH",
    "ПРИЧИННОЕ ПОЛЕ",
    "Декодированный оригинал • живое PCM-поле",
    "Выберите аналитический вид в настройках визуализации",
    "Готово • прямое нативное декодирование",
    "Воспроизведение",
    "Пауза",
    "Воспроизведение завершено",
    "Остановлено",
    "Проверка потока Resonith…",
    "Переход",
    "ПРОСЛУШИВАНИЕ",
    "Громкость",
    "Повтор выключен",
    "Повтор включён",
    "ИСТОЧНИК",
    "Открыть Resonith",
    "Загрузить демо",
    "Настройки",
    "Интерфейс",
    "Язык",
    "Следовать языку системы или выбрать язык интерфейса.",
    "Как в системе",
    "Готово",
    "Поле",
    "Спектр",
    "Волна",
    "История",
    "Локальное воспроизведение • без телеметрии",
    "Прямое воспроизведение .resonith • полностью офлайн",
    "Ошибка воспроизведения",
    "Обзор",
    "Воспроизведение",
    "Аудио",
    "Визуализация",
    "Видео",
    "Субтитры",
    "Медиатека",
    "Производительность",
    "Конфиденциальность",
    "Горячие клавиши",
    "Расширенные",
    "Центр управления",
    "Воспроизвести",
    "Пауза",
    "Продолжить",
    "Стоп",
    "Назад на 10 секунд",
    "Вперёд на 10 секунд",
    "Шкала воспроизведения",
    "Информация о воспроизведении",
};

constexpr text_table ukrainian = {
    "Orkela",
    "Прослуховування без підміни",
    "ЛОКАЛЬНО • ПРИВАТНО",
    "ЗАРАЗ ВІДТВОРЮЄТЬСЯ",
    "Нативний Resonith",
    "Переносна сесія C++23",
    "RESONITH",
    "ПРИЧИННЕ ПОЛЕ",
    "Декодований оригінал • живе PCM-поле",
    "Оберіть аналітичний вигляд у налаштуваннях візуалізації",
    "Готово • пряме нативне декодування",
    "Відтворення",
    "Пауза",
    "Відтворення завершено",
    "Зупинено",
    "Перевірка потоку Resonith…",
    "Перехід",
    "ПРОСЛУХОВУВАННЯ",
    "Гучність",
    "Повтор вимкнено",
    "Повтор увімкнено",
    "ДЖЕРЕЛО",
    "Відкрити Resonith",
    "Завантажити демо",
    "Налаштування",
    "Інтерфейс",
    "Мова",
    "Використовувати мову системи або вибрати мову інтерфейсу.",
    "Як у системі",
    "Готово",
    "Поле",
    "Спектр",
    "Хвиля",
    "Історія",
    "Локальне відтворення • без телеметрії",
    "Пряме відтворення .resonith • повністю офлайн",
    "Помилка відтворення",
    "Огляд",
    "Відтворення",
    "Аудіо",
    "Візуалізація",
    "Відео",
    "Субтитри",
    "Медіатека",
    "Продуктивність",
    "Приватність",
    "Гарячі клавіші",
    "Розширені",
    "Центр керування",
    "Відтворити",
    "Пауза",
    "Продовжити",
    "Стоп",
    "Назад на 10 секунд",
    "Уперед на 10 секунд",
    "Шкала відтворення",
    "Інформація про відтворення",
};

const text_table& table(language selected) noexcept {
    switch (selected) {
    case language::english:
        return english;
    case language::german:
        return german;
    case language::spanish:
        return spanish;
    case language::italian:
        return italian;
    case language::japanese:
        return japanese;
    case language::korean:
        return korean;
    case language::chinese_simplified:
        return chinese_simplified;
    case language::russian:
        return russian;
    case language::ukrainian:
        return ukrainian;
    }
    return english;
}

}  // namespace

language language_from_tag(std::string_view tag) noexcept {
    std::array<char, 16U> normalized{};
    const std::size_t count = std::min(tag.size(), normalized.size() - 1U);
    for (std::size_t index = 0U; index < count; ++index) {
        const unsigned char value =
            static_cast<unsigned char>(tag[index]);
        normalized[index] = value == static_cast<unsigned char>('_')
            ? '-'
            : static_cast<char>(std::tolower(value));
    }
    const std::string_view value(normalized.data(), count);
    const std::size_t separator = value.find('-');
    const std::string_view primary = value.substr(0U, separator);
    if (primary == "de") {
        return language::german;
    }
    if (primary == "es") {
        return language::spanish;
    }
    if (primary == "it") {
        return language::italian;
    }
    if (primary == "ja") {
        return language::japanese;
    }
    if (primary == "ko") {
        return language::korean;
    }
    if (primary == "zh") {
        return language::chinese_simplified;
    }
    if (primary == "ru") {
        return language::russian;
    }
    if (primary == "uk") {
        return language::ukrainian;
    }
    return language::english;
}

std::string_view language_tag(language value) noexcept {
    switch (value) {
    case language::english:
        return "en";
    case language::german:
        return "de";
    case language::spanish:
        return "es";
    case language::italian:
        return "it";
    case language::japanese:
        return "ja";
    case language::korean:
        return "ko";
    case language::chinese_simplified:
        return "zh-Hans";
    case language::russian:
        return "ru";
    case language::ukrainian:
        return "uk";
    }
    return "en";
}

std::string_view language_autonym(language value) noexcept {
    switch (value) {
    case language::english:
        return "English";
    case language::german:
        return "Deutsch";
    case language::spanish:
        return "Español";
    case language::italian:
        return "Italiano";
    case language::japanese:
        return "日本語";
    case language::korean:
        return "한국어";
    case language::chinese_simplified:
        return "简体中文";
    case language::russian:
        return "Русский";
    case language::ukrainian:
        return "Українська";
    }
    return "English";
}

std::string_view localized_text(
    language selected,
    text_id id
) noexcept {
    const std::size_t index = static_cast<std::size_t>(id);
    if (index >= text_count) {
        return {};
    }
    const std::string_view translated = table(selected)[index];
    return translated.empty() ? english[index] : translated;
}

}  // namespace orkela
