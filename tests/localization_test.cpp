#include "orkela/localization.h"

#include <array>
#include <iostream>

int main() {
    using orkela::language;
    constexpr std::array languages = {
        language::english,
        language::german,
        language::spanish,
        language::italian,
        language::japanese,
        language::korean,
        language::chinese_simplified,
        language::russian,
        language::ukrainian,
    };
    for (language selected : languages) {
        if (
            orkela::language_tag(selected).empty()
            || orkela::language_autonym(selected).empty()
        ) {
            std::cerr << "language identity is empty\n";
            return 1;
        }
        for (
            std::size_t index = 0U;
            index < static_cast<std::size_t>(orkela::text_id::count);
            ++index
        ) {
            if (
                orkela::localized_text(
                    selected,
                    static_cast<orkela::text_id>(index)
                ).empty()
            ) {
                std::cerr << "localized text is empty\n";
                return 2;
            }
        }
    }
    if (
        orkela::language_from_tag("de-DE") != language::german
        || orkela::language_from_tag("es_MX") != language::spanish
        || orkela::language_from_tag("ja-JP") != language::japanese
        || orkela::language_from_tag("ko-KR") != language::korean
        || orkela::language_from_tag("zh-CN")
            != language::chinese_simplified
        || orkela::language_from_tag("ru-RU") != language::russian
        || orkela::language_from_tag("uk-UA") != language::ukrainian
        || orkela::language_from_tag("fr-FR") != language::english
    ) {
        std::cerr << "locale tag routing failed\n";
        return 3;
    }
    return 0;
}
