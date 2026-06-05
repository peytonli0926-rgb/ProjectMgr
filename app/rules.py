import re


PATTERN_DEFINITIONS = [
    ("private_key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----", "<PRIVATE_KEY>"),
    ("db_connection", r"(?i)\b(?:jdbc:[^\s'\"]+|mongodb(?:\+srv)?:\/\/[^\s'\"]+|postgres(?:ql)?:\/\/[^\s'\"]+|mysql:\/\/[^\s'\"]+|redis:\/\/[^\s'\"]+|oracle:\/\/[^\s'\"]+)", "<DB_CONNECTION>"),
    ("url_secret_param", r"(?i)([?&](?:password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|auth|session|sid)=)[^&#\s]+", r"\1<REDACTED>"),
    ("id_card", r"(?<!\d)\d{17}[\dXx](?!\d)", "<ID_CARD>"),
    ("passport", r"\b(?:E|G|P|S)\d{8}\b", "<PASSPORT>"),
    ("hk_macao_id", r"\b[A-Z]{1,2}\d{6}[0-9A]\b", "<HK_ID>"),
    ("tw_id", r"\b[A-Z][12]\d{8}\b", "<TW_ID>"),
    ("phone", r"(?<!\d)1[3-9]\d{9}(?!\d)", "<PHONE>"),
    ("fixed_phone", r"(?<!\d)0\d{2,3}[\s-]?\d{7,8}(?!\d)", "<FIXED_PHONE>"),
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<EMAIL>"),
    ("vehicle_plate", r"[\u4e00-\u9fa5][A-Z][A-Z0-9]{5,6}", "<VEHICLE_PLATE>"),
    ("bank_card", r"(?<!\d)(?:\d{13,19}|\d{4}(?:[ -]\d{4}){2,4})(?!\d)", "<BANK_CARD>"),
    ("swift_bic", r"(?i)\b(?!(?:DESCRIPTION|ADDRESS|PROTOCOL|LISTENER|HOSTNAME|DATABASE|INSTANCE|UNIQUE|PRIMARY|STANDARD|SYSTEM|SYSAUX|USERS|TEMP|TOOLS|EXAMPLE|ACCESS|PRIVATE|SECRET|TOKEN|PASSWORD|BIRTHDAY|BALANCE|AMOUNT|ACCOUNT|COMPANY|PERSON|PHONE|EMAIL|CARD|BANK|FQDN|TABLESPACE|DATAFILE|CONTROLFILE|UNDOTBS|DATA|INDEX|LOB|TEMP|RENAME|ALTER|CREATE|DROP|SELECT|INSERT|UPDATE|DELETE|GRANT|REVOKE|COMMIT|ROLLBACK|TRUNCATE|EXECUTE|BEGIN|DECLARE|CURSOR|FETCH|CLOSE|OPEN|LOOP|WHILE|FOR|IF|THEN|ELSE|END|CASE|WHEN|AND|OR|NOT|INTO|FROM|WHERE|HAVING|GROUP|ORDER|BY|ASC|DESC|LIMIT|OFFSET|UNION|ALL|DISTINCT|JOIN|LEFT|RIGHT|INNER|OUTER|CROSS|ON|AS|LIKE|BETWEEN|EXISTS|COUNT|SUM|AVG|MAX|MIN|NULL|TRUE|FALSE|IS|SID|SERIAL|FIRST|LAST|NEXT|PREV|CURRENT|SESSION|SERIAL#|CONNECT\$|RESOURCE|DBA|EXP|IMP|SQL|PLSQL|JAVA|XML|DBMS|UTL|SYS|PUBLIC|PROCEDURE|FUNCTION|PACKAGE|TRIGGER|VIEW|SEQUENCE|SYNONYM|MATERIALIZED|SNAPSHOT|LOG|FILE|MEMBER|LINK|TYPE|BODY|SPECIFICATION|OBJECT|TABLE|INDEX|CLUSTER|HASH|RANGE|LIST|COMPOSITE|PARTITION|SUBPARTITION|LOCAL|GLOBAL|SHARED|EXCLUSIVE|ROW|ROWS|PAGE|BLOCK|EXTENT|SEGMENT|TABLESPACE|DATAFILE|CONTROLFILE|REDO|LOGFILE|ARCHIVE|BACKUP|RECOVER|RMAN|FLASHBACK|PURGE|UNDROP|PASSWORD|PROFILE|ROLE|PRIVILEGE|SYSTEM|SYSAUX|USERS|TEMP|UNDOTBS|EXAMPLE|TOOLS|DATA|INDEX|LOB)[A-Z0-9_]*)\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:XXX|[A-Z0-9]{3})?\b", "<SWIFT_CODE>"),
    ("cnaps_code", r"\b\d{12}\b", "<CNAPS_CODE>"),
    ("bank_account", r"\b\d{15,21}\b", "<BANK_ACCOUNT>"),
    ("security_account", r"\b[A-Z]\d{9,10}\b", "<SECURITY_ACCOUNT>"),
    ("stock_code_sh_sz", r"\b(?:60[0-9]{4}|00[0-9]{4}|30[0-9]{4}|688[0-9]{3}|000[0-9]{4}|002[0-9]{3}|300[0-9]{4})\b", "<STOCK_CODE>"),
    ("fund_code", r"\b(?:50[0-9]{3}|51[0-9]{3}|159[0-9]{3}|16[0-9]{4}|11[0-9]{4}|01[0-9]{4}|00[0-9]{4})\b", "<FUND_CODE>"),
    ("credit_code", r"\b[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}\b", "<CREDIT_CODE>"),
    ("contract_no", r"(?i)\b(?:HT|CON|CTR|AGMT|LOAN|DK|XY)[A-Z0-9]{10,30}\b", "<CONTRACT_NO>"),
    ("transaction_no", r"(?i)\b(?:TXN|TRX|VCH|BIL|SEQ|SER|ORD)[A-Z0-9]{12,30}\b", "<TXN_NO>"),
    ("invoice_no", r"\b\d{8,12}\b", "<INVOICE_NO>"),
    ("taxpayer_id", r"\b(?:\d{15}|\d{18}|\d{20})\b", "<TAXPAYER_ID>"),
    ("ipv6", r"\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{1,4}\b", "<IP>"),
    ("ip", r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b", "<IP>"),
    ("mac", r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b", "<MAC>"),
    ("url_hostname", r"(?i)\b((?:https?|ftp)://)(?!<IP>)([A-Za-z0-9][A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,})(?=[:/?#]|$)", r"\1<HOSTNAME>"),
    ("fqdn_hostname", r"(?i)\b(?!<HOSTNAME>)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+(?:local|lan|internal|intranet|corp|bank|com|cn|net|org)\b", "<HOSTNAME>"),
    ("table_hostname_field", r"(?i)\b(HOST_NAME|HOSTNAME|SERVER_NAME|MACHINE_NAME|主机名|服务器名|节点名)\s+((?=[A-Za-z0-9._-]*(?:\d|db|app|web|srv|host|node|rac|scan|ora))[A-Za-z][A-Za-z0-9._-]{1,253})\b", r"\1 <HOSTNAME>"),
    # ────────── 数据库 / TFA / AWR 运维敏感信息 ──────────
    ("awr_db_info_table", r"(?i)\b(DB Name|DB Id|Unique Name|Instance Name|Host Name|数据库名|实例名|节点名)\s*[:：]?\s+[A-Za-z0-9_#]{3,30}\b", "<DB_INFO>"),
    ("oracle_env_var", r"(?i)(?:ORACLE_SID|ORACLE_HOME|ORACLE_BASE|ORACLE_UNQNAME|TNS_ADMIN|LD_LIBRARY_PATH|ORA_NLS|NLS_LANG)\s*=\s*['\"]?[^\s'\"\r\n]+['\"]?", "<DB_ENV_VAR>"),
    ("datafile_path", r"(?i)[/\\](?:u0[1-9]|oradata|oracle|app[/\\](?:admin|oracle))[\w\-\./\\]+\.(?:dbf|log|ctl|ora|dat|arc|trc|trm|pdb)\b", "<DB_FILE_PATH>"),
    ("asm_diskgroup", r"(?i)\b(?:\+DATA|\+FRA|\+RECO|\+ARCH|\+OCR_VOTE|\+SYSTEMG|\+BACKUP)(?=[/\s]|$)", "<ASM_DISKGROUP>"),
    ("oracle_system_tables", r"\b(?:DBA_|ALL_|USER_|V_(?:\$|\\$)|GV_(?:\$|\\$)|X\$|CDB_)[A-Z][A-Z0-9_#\$]{1,30}\b", "<DB_OBJECT>"),
    ("tbspace_standard_names", r"(?i)\b(?:tablespace_name|表空间名|表空间)\s*[:=：]\s*(?:SYSTEM|SYSAUX|USERS|UNDOTBS[0-9]*|TEMP|TOOLS|EXAMPLE|DATA|INDEX|LOB)\b", r"<DB_OBJECT>"),
    ("pdb_names", r"(?i)\b(?:PDB|CDB|PDB\$SEED)\b", "<PDB_NAME>"),
    ("listener_config", r"(?i)\bLISTENER\s*=\s*\(DESCRIPTION", "<LISTENER>"),
    ("generic_infra_hostname", r"(?i)(?<![:./@A-Za-z0-9-])(?=[A-Za-z0-9-]*(?:db|app|web|srv|host|node|rac|scan|ora|oracle))(?=[A-Za-z0-9-]*\d)[A-Za-z][A-Za-z0-9-]{2,63}\b", "<HOSTNAME>"),
    ("secret_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|private[_-]?key|session|sid|cookie|auth_token|refresh_token|app_secret|client_secret)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}\r\n]+(['\"]?)", r"\1<REDACTED>\2"),
    ("hostname_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:host|hostname|host_name|server|server_name|machine|machine_name)['\"]?\s*[:=]\s*['\"]?)[A-Za-z0-9][A-Za-z0-9._-]{1,253}(['\"]?)", r"\1<HOSTNAME>\2"),
    ("name_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:name|real_name|full_name|customer_name|user_name|contact_person|applicant|counterparty|beneficiary|姓名|客户姓名|用户姓名|联系人)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<NAME>\2"),
    ("address_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:address|addr|home_address|work_address|mailing_address|billing_address|住址|地址|家庭住址|办公地址|通讯地址)['\"]?\s*[:=]\s*['\"]?).+?(?=\s+[A-Za-z_\u4e00-\u9fa5]+\s*[:=]|[;}；\r\n]|$)(['\"]?)", r"\1<ADDRESS>\2"),
    ("location_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:location|gps|longitude|latitude|lat|lon|lng|行踪|位置|经度|纬度)['\"]?\s*[:=]\s*['\"]?).+?(?=\s+[A-Za-z_\u4e00-\u9fa5]+\s*[:=]|[;}；\r\n]|$)(['\"]?)", r"\1<LOCATION>\2"),
    ("birth_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:birthday|birth_date|date_of_birth|dob|出生日期|出生年月)['\"]?\s*[:=]\s*['\"]?)\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?(['\"]?)", r"\1<DATE>\2"),
    ("account_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:account|account_no|user_id|userid|username|login_name|member_id|cif_id|cust_id|customer_id|账号|账户|用户名|客户号)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<ACCOUNT>\2"),
    ("financial_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:bank_account|card_no|card_number|salary|income|balance|amount|loan_amount|principal|interest|overdue_amount|credit_limit|available_balance|月薪|年薪|收入|余额|贷款金额|授信额度|逾期金额|本金|利息)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<FINANCIAL_INFO>\2"),
    ("rate_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:interest_rate|annual_rate|monthly_rate|apr|lending_rate|年利率|月利率|日利率|费率)['\"]?\s*[:=]\s*['\"]?)\d+(?:\.\d+)?%?(['\"]?)", r"\1<RATE>\2"),
    ("credit_score_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:credit_score|risk_score|rating|credit_rating|芝麻分|信用评分|风控评分|风险等级)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<CREDIT_SCORE>\2"),
    ("loan_status_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:loan_status|repayment_status|overdue_days|五级分类|贷款五级分类|贷款状态|还款状态|逾期天数)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<LOAN_STATUS>\2"),
    ("collateral_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:collateral|抵押物|质押物|担保物|mortgage|pledge)['\"]?\s*[:=]\s*['\"]?).+?(?=\s+[A-Za-z_\u4e00-\u9fa5]+\s*[:=]|[;}；\r\n]|$)(['\"]?)", r"\1<COLLATERAL>\2"),
    ("company_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:company_name|company|enterprise_name|corp_name|firm|org_name|单位名称|企业名称|公司名称)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]{2,100}(['\"]?)", r"\1<COMPANY_NAME>\2"),
    ("legal_person_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:legal_person|legal_representative|法人代表|法定代表人|董事长|director)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<LEGAL_PERSON>\2"),
    ("aml_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:aml_flag|aml_status|sanction_list|pep_flag|blacklist|watchlist|反洗钱|制裁名单|黑名单|敏感名单|政治人物)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<AML_INFO>\2"),
    ("compliance_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:compliance_status|approval_status|regulatory_approval|licence_no|license_no|合规状态|监管意见|批准文号|批复文号|备案号|许可证号)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<COMPLIANCE_INFO>\2"),
    ("medical_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:medical_record|patient_id|diagnosis|disease|hospital|病历号|患者编号|诊断|疾病|医院)['\"]?\s*[:=]\s*['\"]?).+?(?=\s+[A-Za-z_\u4e00-\u9fa5]+\s*[:=]|[;}；\r\n]|$)(['\"]?)", r"\1<MEDICAL_INFO>\2"),
    ("biometric_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:face_id|face_image|fingerprint|voiceprint|iris|biometric|人脸|指纹|声纹|虹膜|生物识别)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<BIOMETRIC>\2"),
    ("religion_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:religion|religious_belief|宗教|宗教信仰)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<RELIGION>\2"),
    ("minor_field", r"(?i)(?<![A-Za-z0-9_])(['\"]?(?:guardian|minor|child_name|儿童姓名|未成年人|监护人)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,;}，；\r\n]+(['\"]?)", r"\1<MINOR_INFO>\2"),
]

SENSITIVE_PATTERNS = [(name, re.compile(pattern), replacement) for name, pattern, replacement in PATTERN_DEFINITIONS]


def merge_counts(total, delta):
    for key, value in delta.items():
        total[key] = total.get(key, 0) + value


def redact_text(text: str):
    counts = {}
    redacted = text
    for name, pattern, replacement in SENSITIVE_PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            counts[name] = counts.get(name, 0) + count
    return redacted, counts


def xml_safe_replacement(replacement):
    if not isinstance(replacement, str):
        return replacement
    return replacement.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def redact_xml_text(text: str):
    counts = {}
    redacted = text
    for name, pattern, replacement in SENSITIVE_PATTERNS:
        redacted, count = pattern.subn(xml_safe_replacement(replacement), redacted)
        if count:
            counts[name] = counts.get(name, 0) + count
    return redacted, counts


def redact_office_xml(xml_text: str):
    counts = {}

    def redact_between_tags(match):
        redacted, delta = redact_xml_text(match.group(1))
        merge_counts(counts, delta)
        return f">{redacted}<"

    return re.sub(r">([^<]*)<", redact_between_tags, xml_text), counts


def redact_html_text(html_text: str):
    """对 HTML 内容脱敏，保留标签结构不破坏。"""
    counts = {}

    def redact_text_outside_tags(match):
        before_tag = match.group(1)
        tag = match.group(2)
        redacted, delta = redact_text(before_tag)
        merge_counts(counts, delta)
        return f"{redacted}{tag}"

    # 先处理 <script>/<style> 块中的内容（跳过它们内部的敏感文本，仅处理普通文本区域）
    def skip_script_style(whole_match):
        return whole_match

    # 策略：对 HTML 中的纯文本部分（tag 之间的内容）做脱敏
    redacted = re.sub(r"([^<]*)(<[^>]+>)", redact_text_outside_tags, html_text)
    # 处理最后一段文本（如果没有尾部标签）
    if redacted.rstrip().endswith(">"):
        pass  # 已处理
    else:
        # 处理末尾纯文本
        parts = redacted.rsplit(">", 1)
        if len(parts) == 2:
            tail_text = parts[1]
            redacted_tail, delta = redact_text(tail_text)
            merge_counts(counts, delta)
            redacted = parts[0] + ">" + redacted_tail
    return redacted, counts
