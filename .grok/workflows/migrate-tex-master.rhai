let meta = #{
    name: "migrate-tex-master",
    description: "Create branch master, convert 17 Markdown books to TeX, verify PDFs, then drop Markdown/EPUB on that branch only",
    when_to_use: "migrate to TeX-canonical master branch, convert markdown to tex, 迁到 master 用 TeX 维护",
    phases: [
        #{ title: "Bootstrap", detail: "create master, convert Markdown to tex/books" },
        #{ title: "Review", detail: "one editor per volume, structural TeX cleanup only" },
        #{ title: "Verify", detail: "compile TeX PDFs and confirm raw/ PNG stay" },
        #{ title: "Prune", detail: "remove Markdown and EPUB from master after verify" },
        #{ title: "Report", detail: "write a run summary" },
    ],
};

fn trimmed(s) {
    if type_of(s) == "string" {
        s.trim();
        s
    } else {
        ""
    }
}

let mode = "full";
let book = "";
if args != () {
    if args.mode != () { mode = args.mode; }
    if args.book != () { book = args.book; }
}
if mode != "full" && mode != "one" {
    pause("verification", "args.mode must be \"full\" or \"one\".");
}
if mode == "one" && book == "" {
    pause("verification", "one-book mode needs args.book, e.g. 代数（第一册）.");
}

let titles = [
    "代数（第一册）",
    "代数（第二册）",
    "代数（第三册）",
    "代数（第四册）",
    "平面三角",
    "平面几何（第一册）",
    "平面几何（第二册）",
    "平面解析几何",
    "立体几何",
    "化学（第一册）",
    "化学（第二册）",
    "化学（第三册）",
    "化学（第四册）",
    "物理（第一册）",
    "物理（第二册）",
    "物理（第三册）",
    "物理（第四册）",
];
if mode == "one" {
    titles = [book];
}

let bootstrap_schema = #{
    "type": "object",
    "required": ["ok", "branch", "converted", "notes"],
    "properties": #{
        "ok": #{ "type": "boolean" },
        "branch": #{ "type": "string" },
        "converted": #{ "type": "array", "items": #{ "type": "string" } },
        "notes": #{ "type": "string" },
    },
};
let review_schema = #{
    "type": "object",
    "required": ["title", "ok", "changed", "notes"],
    "properties": #{
        "title": #{ "type": "string" },
        "ok": #{ "type": "boolean" },
        "changed": #{ "type": "boolean" },
        "notes": #{ "type": "string" },
    },
};
let verify_schema = #{
    "type": "object",
    "required": ["ok", "pdf_pass", "raw_untouched", "png_present", "notes"],
    "properties": #{
        "ok": #{ "type": "boolean" },
        "pdf_pass": #{ "type": "boolean" },
        "raw_untouched": #{ "type": "boolean" },
        "png_present": #{ "type": "boolean" },
        "notes": #{ "type": "string" },
    },
};
let prune_schema = #{
    "type": "object",
    "required": ["ok", "deleted", "notes"],
    "properties": #{
        "ok": #{ "type": "boolean" },
        "deleted": #{ "type": "array", "items": #{ "type": "string" } },
        "notes": #{ "type": "string" },
    },
};

phase("Bootstrap");
let boot_prompt = "";
boot_prompt += "You are bootstrapping the TeX-canonical git branch for this repo. Work in the current workspace. ";
boot_prompt += "Do not push. Do not change GitHub default branch. Do not force-push. Do not rewrite main history.\n\n";
boot_prompt += "Hard rules:\n";
boot_prompt += "1. Branch name MUST be master.\n";
boot_prompt += "2. Keep raw/ byte-for-byte. Keep books/assets PNG files. Do not delete Markdown yet.\n";
boot_prompt += "3. Canonical TeX outputs go to tex/books/<title>.tex matching catalog.json titles.\n";
boot_prompt += "4. Use existing scripts; do not invent a second converter.\n\n";
boot_prompt += "Steps (idempotent):\n";
boot_prompt += "- Run git status and git branch. If HEAD is not already master, create/switch with `git checkout -b master` or `git checkout master`. If master exists, use it.\n";
boot_prompt += "- Copy tex/BRANCH_AGENTS.md over AGENTS.md on this branch (preserve a copy as tex/BRANCH_AGENTS.md).\n";
if mode == "one" {
    boot_prompt += "- Run: python3 scripts/convert_md_to_tex.py --book ";
    boot_prompt += json_encode(book);
    boot_prompt += "\n";
} else {
    boot_prompt += "- Run: python3 scripts/convert_md_to_tex.py\n";
}
boot_prompt += "- Confirm each converted file exists under tex/books/ and contains \\begin{document}.\n";
boot_prompt += "- Stage only TeX-migration files (tex/, scripts/convert_md_to_tex.py, scripts/build_pdfs.py, scripts/audit_tex_sources.py, scripts/audit_repository.py, Makefile, catalog.json, AGENTS.md, .grok/workflows/migrate-tex-master.rhai, related docs). Do not stage dist/ or .build/.\n";
boot_prompt += "- Create a commit on master if there are staged changes, message: Add TeX book sources and PDF build tooling for the master branch.\n";
boot_prompt += "- Do not push. Do not commit on main.\n";
boot_prompt += "Return ok=true only if conversion succeeded for the requested titles. List converted titles. notes = commands you ran and any errors.";

let boot = agent(boot_prompt, #{
    label: "bootstrap-master",
    capability_mode: "all",
    output_schema: bootstrap_schema,
});
if boot == () || !boot.success || boot.output.ok != true {
    complete(#{
        summary: "Bootstrap failed; master conversion did not complete.",
        mode: mode,
        ok: false,
    });
}
let converted_n = 0;
if boot.output.converted != () {
    converted_n = boot.output.converted.len();
}
let branch_name = "";
if boot.output.branch != () {
    branch_name = boot.output.branch;
}
log("bootstrap converted " + converted_n.to_string() + " book(s) on " + branch_name);

phase("Review");
let jobs = [];
for title in titles {
    let prompt = "";
    prompt += "Structurally clean the TeX source for one volume. Do not rewrite textbook content. ";
    prompt += "Do not delete images. Do not edit books/*.md, raw/, or other volumes.\n\n";
    prompt += "Title (JSON): " + json_encode(title) + "\n";
    prompt += "File: tex/books/<title>.tex\n\n";
    prompt += "Use read_file/grep/search_replace. You must open the actual .tex file before editing.\n";
    prompt += "Allowed fixes only: unmatched braces, broken \\includegraphics paths (must stay under books/assets or assets/), ";
    prompt += "duplicate \\maketitle/\\tableofcontents, leftover Markdown fences, obviously truncated environments. ";
    prompt += "If the file already compiles structurally, change nothing and set changed=false.\n";
    prompt += "Set ok=true if the file still has \\begin{document}/\\end{document} after your pass.";
    jobs.push(#{
        prompt: prompt,
        label: "review:" + title,
        capability_mode: "read-write",
        output_schema: review_schema,
    });
}
let reviews = parallel(jobs);
let review_ok = 0;
let review_fail = 0;
for r in reviews {
    if r != () && r.success && r.output.ok == true {
        review_ok += 1;
    } else {
        review_fail += 1;
    }
}
log("review ok=" + review_ok.to_string() + " fail=" + review_fail.to_string());

phase("Verify");
let verify_prompt = "";
verify_prompt += "Verify the TeX-canonical master branch. Do not push. Do not delete sources in this step.\n";
verify_prompt += "Requested titles (JSON): " + json_encode(titles) + "\n";
verify_prompt += "Mode: " + mode + "\n\n";
verify_prompt += "Run these commands from the repo root and read their output:\n";
if mode == "one" {
    verify_prompt += "1. python3 scripts/audit_tex_sources.py (may fail if only one tex book exists; then instead confirm tex/books/<title>.tex exists)\n";
    verify_prompt += "2. python3 scripts/build_pdfs.py --from-tex --skip-collections --book ";
    verify_prompt += json_encode(book);
    verify_prompt += " --jobs 1\n";
} else {
    verify_prompt += "1. python3 scripts/audit_tex_sources.py\n";
    verify_prompt += "2. python3 scripts/build_pdfs.py --from-tex --jobs 2\n";
}
verify_prompt += "3. Confirm raw/ still has 17 PDFs and SHA256SUMS.txt.\n";
verify_prompt += "4. Confirm books/assets still has PNG files (find books/assets -name '*.png' | wc -l should be 4875).\n";
verify_prompt += "Set pdf_pass=true only if the build command printed status PASS or the selected book PASS.\n";
verify_prompt += "Set raw_untouched=true only after listing raw/*.pdf count=17.\n";
verify_prompt += "Set png_present=true only if PNG count is 4875.\n";
verify_prompt += "ok=true only if pdf_pass and raw_untouched and png_present.";

let verify = agent(verify_prompt, #{
    label: "verify-tex-pdf",
    capability_mode: "all",
    output_schema: verify_schema,
});
let verify_ok = verify != () && verify.success && verify.output.ok == true;
if !verify_ok {
    complete(#{
        summary: "Verify failed; Markdown/EPUB were not pruned.",
        mode: mode,
        ok: false,
        review_ok: review_ok,
        review_fail: review_fail,
        verify: if verify != () && verify.success { verify.output } else { () },
    });
}

if mode == "one" {
    complete(#{
        summary: "One-book conversion verified; prune skipped in one mode.",
        mode: mode,
        ok: true,
        book: book,
        review_ok: review_ok,
    });
}

phase("Prune");
let prune_prompt = "";
prune_prompt += "Verification passed. Prune Markdown and EPUB from branch master only. Do not touch main. Do not push.\n";
prune_prompt += "Delete these paths if they exist: books/*.md matching '* - 数理化自学丛书编委会.md', epub/, scripts/build_epubs.py.\n";
prune_prompt += "Keep: raw/, books/assets/, tex/, scripts/convert_md_to_tex.py, scripts/build_pdfs.py, scripts/audit_tex_sources.py, catalog.json, Makefile.\n";
prune_prompt += "Overwrite AGENTS.md with tex/BRANCH_AGENTS.md if not already identical.\n";
prune_prompt += "Update Makefile so `pdf` runs `$(PYTHON) scripts/build_pdfs.py --from-tex` and `audit` runs tex-audit. Keep pdf-tex as an alias.\n";
prune_prompt += "Update scripts/audit_repository.py REQUIRED: remove epub/epub.css, epub/wrap_tables.lua, epub/pandoc-data/translations/zh-CN.yaml, scripts/build_epubs.py if those files were deleted; add scripts/convert_md_to_tex.py and scripts/audit_tex_sources.py if missing.\n";
prune_prompt += "Do not delete PNG files. Do not delete raw/.\n";
prune_prompt += "Commit on master only, message: Remove Markdown and EPUB sources from the TeX-canonical master branch. Do not push.\n";
prune_prompt += "Return deleted as repo-relative paths you actually removed. ok=true only if Markdown book files are gone from this branch and tex/books still has 17 files.";

let prune = agent(prune_prompt, #{
    label: "prune-markdown-epub",
    capability_mode: "all",
    output_schema: prune_schema,
});

phase("Report");
let ok = prune != () && prune.success && prune.output.ok == true;
let summary = if ok {
    "master branch now uses TeX sources; Markdown/EPUB removed on master only."
} else {
    "Conversion verified but prune did not fully succeed; inspect the working tree."
};
let report = "";
report += "# migrate-tex-master\n\n";
report += summary + "\n\n";
report += "- mode: " + mode + "\n";
report += "- review_ok: " + review_ok.to_string() + "\n";
report += "- review_fail: " + review_fail.to_string() + "\n";
let report_path = write_scratch_file("migrate-tex-master-report.md", report);
complete(#{
    summary: summary,
    mode: mode,
    ok: ok,
    review_ok: review_ok,
    review_fail: review_fail,
    report: report_path,
});
