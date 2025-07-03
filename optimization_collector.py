import arxiv
import feedparser
import requests
from datetime import datetime, timedelta
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import sys
import pytz
import time
from transformers import pipeline, M2M100ForConditionalGeneration, M2M100Tokenizer
import torch

class OptimizationNewsCollector:
    def __init__(self):
        # 環境変数から設定を取得
        self.recipient_email = os.getenv('RECIPIENT_EMAIL')
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('GMAIL_APP_PASSWORD')
        
        # 日本時間のタイムゾーン設定
        self.jst = pytz.timezone('Asia/Tokyo')

        # M2M100翻訳モデルの初期化
        self.setup_translation_model()
        
        # 優先度の高いキーワード（積付計画最適化、配送計画問題、スケジューリング問題）
        self.priority_keywords = [
            'packing', 'bin packing', 'container packing', 'loading',
            'vehicle routing', 'delivery', 'distribution', 'logistics',
            'scheduling', 'task scheduling', 'job scheduling', 'resource scheduling',
            'timetabling', 'workforce scheduling'
        ]

    def setup_translation_model(self):
        """M2M100翻訳モデルをセットアップ（キャッシュ対応）"""
        print("🔧 M2M100翻訳モデルを初期化中...")
        
        # キャッシュディレクトリの設定
        cache_dir = os.getenv('TRANSFORMERS_CACHE', './model_cache')
        os.makedirs(cache_dir, exist_ok=True)
        
        try:
            # M2M100-418Mモデルを使用（より高精度）
            model_name = "facebook/m2m100_418M"
            
            # デバイス設定（GPU利用可能ならGPU、そうでなければCPU）
            device = 0 if torch.cuda.is_available() else -1
            
            # トークナイザーとモデルを個別に読み込み
            self.tokenizer = M2M100Tokenizer.from_pretrained(
                model_name,
                cache_dir=cache_dir
            )
            self.model = M2M100ForConditionalGeneration.from_pretrained(
                model_name,
                cache_dir=cache_dir
            )
            
            # デバイスに移動
            if torch.cuda.is_available():
                self.model = self.model.cuda()
                print("✅ GPU使用でM2M100を初期化しました")
            else:
                print("✅ CPU使用でM2M100を初期化しました")
                
        except Exception as e:
            print(f"❌ M2M100初期化エラー: {e}")
            print("フォールバック: 簡単な翻訳パイプラインを使用します")
            try:
                self.translation_pipeline = pipeline(
                    "translation_en_to_ja", 
                    model="staka/fugumt-en-ja",
                    cache_dir=cache_dir
                )
                self.model = None
                self.tokenizer = None
                print("✅ フォールバック翻訳モデルを初期化しました")
            except Exception as e2:
                print(f"❌ フォールバック翻訳モデル初期化エラー: {e2}")
                self.translation_pipeline = None
                self.model = None
                self.tokenizer = None
   
    def get_jst_time(self):
        """現在の日本時間を取得"""
        return datetime.now(self.jst)

    def translate_text(self, text, max_length=2048):
        """M2M100を使用してテキストを英語から日本語に翻訳"""
        if not text or text.strip() == "":
            return ""
        
        # テキストの前処理
        text = text.strip()
        if len(text) > 1000:  # 長すぎるテキストは切り詰める
            text = text[:1000] + "..."
        
        try:
            if self.model and self.tokenizer:
                # M2M100を使用した翻訳
                self.tokenizer.src_lang = "en"
                encoded = self.tokenizer(text, return_tensors="pt", max_length=512, truncation=True)
                
                # デバイスに移動
                if torch.cuda.is_available():
                    encoded = {k: v.cuda() for k, v in encoded.items()}
                
                # 翻訳実行
                generated_tokens = self.model.generate(
                    **encoded,
                    forced_bos_token_id=self.tokenizer.get_lang_id("ja"),
                    max_length=max_length,
                    num_beams=5,
                    early_stopping=True
                )
                
                translated = self.tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
                return translated
                
            elif self.translation_pipeline:
                # フォールバック翻訳
                result = self.translation_pipeline(text, max_length=max_length)
                return result[0]['translation_text']
            else:
                # 翻訳不可の場合
                return "(翻訳不可)"
                
        except Exception as e:
            print(f"⚠️ 翻訳エラー: {e}")
            return "(翻訳失敗)"

    def calculate_priority_score(self, title, summary=""):
        """優先度スコアを計算（積付計画最適化、配送計画問題、スケジューリング問題を最優先）"""
        combined_text = (title + " " + summary).lower()
        
        # 優先キーワードのスコア計算
        priority_score = 0
        for keyword in self.priority_keywords:
            if keyword in combined_text:
                priority_score += 10  # 高い優先度スコア
        
        # 一般的な最適化キーワードのスコア
        general_keywords = [
            'optimization', 'optimisation', 'algorithm', 'programming',
            'linear programming', 'integer programming', 'convex',
            'mathematical programming', 'constraint', 'heuristic'
        ]
        
        for keyword in general_keywords:
            if keyword in combined_text:
                priority_score += 1
        
        return priority_score

    def simple_arxiv_test(self):
        """最もシンプルなarXivテスト（修正版）"""
        print("最新5件の math.OC 論文:")
        
        try:
            # Method 1: arxivライブラリを使用（修正版）
            client = arxiv.Client()
            
            # より安全な設定
            search = arxiv.Search(
                query="cat:math.OC",
                max_results=5,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            # リトライ機能付きで実行
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries:
                try:
                    results = list(client.results(search))
                    break
                except (arxiv.arxiv.HTTPError, requests.exceptions.RequestException) as e:
                    retry_count += 1
                    print(f"  ⚠️ 試行 {retry_count}/{max_retries} でエラー: {e}")
                    if retry_count < max_retries:
                        print(f"  ⏳ {2 ** retry_count}秒後にリトライします...")
                        time.sleep(2 ** retry_count)  # 指数バックオフ
                    else:
                        print("  ❌ arxivライブラリでの取得に失敗しました。代替方法を試します...")
                        return self.fallback_arxiv_test()
            
            for i, result in enumerate(results, 1):
                print(f"{i}. {result.title}")
                print(f"   Published: {result.published}")
                print(f"   URL: {result.entry_id}")
                print()
                
            print(f"✅ arxivライブラリで {len(results)} 件取得成功")
            return True
            
        except Exception as e:
            print(f"❌ arxivライブラリでエラー: {e}")
            return False
        
    def collect_arxiv_papers_fixed(self, days_back=2):
        """修正版：arXivから数理最適化関連論文を収集"""
        print("📚 arXivから論文を収集中...")
        
        papers = []
        cutoff_date = self.get_jst_time().date() - timedelta(days=days_back)
        
        # Method 1: arxivライブラリを試す
        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=(
                    "cat:math.OC OR "
                    "(cat:cs.DM AND (optimization OR programming OR algorithm)) OR "
                    "(cat:stat.ML AND optimization) OR "
                    'ti:"linear programming" OR ti:"integer programming" OR '
                    'ti:"convex optimization" OR ti:"nonlinear programming" OR '
                    'ti:"combinatorial optimization" OR ti:"stochastic optimization" OR '
                    'ti:"packing" OR ti:"scheduling" OR ti:"vehicle routing"'
                ),
                max_results=50,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            # リトライ機能付きで実行
            results = []
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries:
                try:
                    results = list(client.results(search))
                    break
                except Exception as e:
                    retry_count += 1
                    print(f"  ⚠️ arxivライブラリ試行 {retry_count}/{max_retries} でエラー: {e}")
                    if retry_count < max_retries:
                        time.sleep(2 ** retry_count)
                    else:
                        print("  ❌ arxivライブラリに失敗、直接API呼び出しを試します...")
                        return self.collect_arxiv_papers_direct_api(days_back)
            
            # 結果を処理
            for result in results:
                published_jst = result.published.astimezone(self.jst).date()
                updated_jst = result.updated.astimezone(self.jst).date() if result.updated else None
                
                if published_jst >= cutoff_date or (updated_jst and updated_jst >= cutoff_date):
                    # 翻訳実行
                    print(f"  📝 翻訳中: {result.title[:50]}...")
                    translated_title = self.translate_text(result.title)
                    translated_summary = self.translate_text(result.summary)
                    
                    # 優先度スコア計算
                    priority_score = self.calculate_priority_score(result.title, result.summary)

                    papers.append({
                        'title': translated_title,
                        'original_title': result.title.replace('\n', ' ').strip(),
                        'authors': [author.name for author in result.authors[:3]],
                        'abstract': translated_summary,
                        'original_abstract': result.summary.replace('\n', ' ').strip()[:500] + "...",
                        'url': result.entry_id,
                        'published': published_jst.strftime('%Y-%m-%d'),
                        'updated': updated_jst.strftime('%Y-%m-%d') if updated_jst else None,
                        'categories': result.categories,
                        'priority_score': priority_score
                    })
            
            print(f"✅ arxivライブラリで論文 {len(papers)} 件を収集しました")
            return papers
            
        except Exception as e:
            print(f"❌ arxivライブラリでエラー: {e}")
            print("直接API呼び出しを試します...")
            return papers

    def collect_news_from_rss_improved(self):
        """改善版：RSSから最適化関連ニュースを収集"""
        print("📰 ニュースを収集中...")
        
        # より現在でも使えるRSSソース（2024年対応）
        rss_urls = [
            # より確実に動作するRSSフィード
            "https://www.theverge.com/rss/index.xml",
            "https://techcrunch.com/feed/",
            "https://www.wired.com/feed/rss",
            "https://arstechnica.com/feed/",
            "https://feeds.feedburner.com/venturebeat/SZYF",
            "https://www.zdnet.com/news/rss.xml"
        ]
#            "https://rss.cnn.com/rss/edition_technology.rss",    #アクセスエラー
#            "https://feeds.reuters.com/reuters/technologyNews"    #アクセスエラー

        
        # より柔軟なキーワードフィルタ（段階的アプローチ）
        # Tier 1: 直接関連（高スコア）
        high_priority_keywords = [
            'optimization', 'optimisation', 'algorithm', 'programming',
            'machine learning', 'AI', 'artificial intelligence',
            'data science', 'operations research', 'solver'
        ]
        
        # Tier 2: 間接関連（中スコア）
        medium_priority_keywords = [
            'analytics', 'efficiency', 'performance', 'automation',
            'neural network', 'deep learning', 'model', 'prediction',
            'computational', 'mathematical', 'statistical'
        ]
        
        # Tier 3: 技術関連（低スコア）
        low_priority_keywords = [
            'software', 'technology', 'tech', 'innovation',
            'research', 'development', 'computing', 'digital'
        ]
        
        # 除外キーワードを減らす（過度な除外を防ぐ）
        exclude_keywords = [
            'celebrity', 'entertainment', 'sports', 'weather',
            'crime', 'accident', 'war', 'fashion', 'food', 'travel'
        ]
        
        news_items = []
        
        for rss_url in rss_urls:
            try:
                print(f"  🔍 取得中: {rss_url}")
                
                # タイムアウトとユーザーエージェントを設定
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                # まずHTTPでアクセス可能かチェック
                try:
                    response = requests.get(rss_url, headers=headers, timeout=10)
                    if response.status_code != 200:
                        print(f"    ⚠️ HTTP {response.status_code}: {rss_url}")
                        continue
                except Exception as e:
                    print(f"    ⚠️ アクセスエラー: {e}")
                    continue
                
                # feedparserで解析
                feed = feedparser.parse(rss_url)
                
                if not feed.entries:
                    print(f"    ⚠️ エントリなし: {rss_url}")
                    continue
                
                print(f"    ✅ {len(feed.entries)}件のエントリを取得")
                
                # より多くのエントリをチェック（20件に増加）
                for entry in feed.entries[:20]:
                    try:
                        title_lower = entry.title.lower()
                        summary_lower = getattr(entry, 'summary', '').lower()
                        combined_text = title_lower + ' ' + summary_lower
                        
                        # 除外キーワードチェック（緩和）
                        exclude_count = sum(1 for exclude in exclude_keywords 
                                          if exclude in combined_text)
                        if exclude_count >= 2:  # 2個以上の除外キーワードがある場合のみ除外
                            continue
                        
                        # 段階的関連度スコア計算
                        high_score = sum(4 for keyword in high_priority_keywords 
                                       if keyword in combined_text)
                        medium_score = sum(2 for keyword in medium_priority_keywords 
                                         if keyword in combined_text)
                        low_score = sum(1 for keyword in low_priority_keywords 
                                      if keyword in combined_text)
                        
                        total_relevance_score = high_score + medium_score + low_score
                        
                        # より緩い閾値（2.0以上で採用）
                        if total_relevance_score >= 2.0:
                            # 日本時間で公開日を処理
                            published_date = getattr(entry, 'published', '')
                            if published_date:
                                try:
                                    # より柔軟な日付パース
                                    from dateutil import parser
                                    pub_dt = parser.parse(published_date)
                                    if pub_dt.tzinfo is None:
                                        pub_dt = pytz.utc.localize(pub_dt)
                                    published_jst = pub_dt.astimezone(self.jst).strftime('%Y-%m-%d %H:%M JST')
                                except:
                                    published_jst = published_date[:19] if len(published_date) > 19 else published_date
                            else:
                                published_jst = '日時不明'
                            
                            # 重複チェック（URLベース）
                            if not any(item['link'] == entry.link for item in news_items):
                                # 翻訳実行
                                print(f"    📝 翻訳中: {entry.title[:50]}...")
                                translated_title = self.translate_text(entry.title)
                                translated_summary = self.translate_text(getattr(entry, 'summary', ''))

                                news_items.append({
                                    'title': translated_title,
                                    'original_title': entry.title.strip(),
                                    'link': entry.link,
                                    'published': published_jst,
                                    'summary': translated_summary,
                                    'original_summary': getattr(entry, 'summary', '')[:300] + "...",
                                    'relevance_score': round(total_relevance_score, 1),
                                    'priority_score': priority_score,
                                    'source_url': rss_url
                                })
                                
                                print(f"    📄 採用: {entry.title[:50]}... (スコア: {total_relevance_score:.1f})")
                    
                    except Exception as e:
                        print(f"    ⚠️ エントリ処理エラー: {e}")
                        continue
                        
            except Exception as e:
                print(f"  ❌ RSS取得エラー ({rss_url}): {e}")
                continue
            
            # API制限を考慮して少し待機
            time.sleep(0.5)
        
        # 関連度スコア順でソート
        news_items.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        # 上位10件に制限（元の5件から増加）
        news_items = news_items[:10]
        
        print(f"✅ 関連ニュース {len(news_items)} 件を収集しました")
        
        # デバッグ情報の出力
        if news_items:
            print("📊 収集されたニュースの詳細:")
            for i, item in enumerate(news_items, 1):
                print(f"  {i}. スコア{item['relevance_score']}: {item['title'][:60]}...")
        else:
            print("⚠️ フィルタリング後のニュースが0件です。以下を確認してください：")
            print("  1. RSSフィードのアクセス状況")
            print("  2. キーワードフィルタの設定")
            print("  3. 除外キーワードの設定")
        
        return news_items
    
    def generate_html_report(self, papers, news_items):
        """美しいHTMLレポートを生成"""
        jst_now = self.get_jst_time()
        
        # HTMLテンプレート
        html_report = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>数理最適化 日次レポート</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                    color: #333;
                }}
                .container {{
                    max-width: 800px;
                    margin: 0 auto;
                    background-color: white;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    overflow: hidden;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                    font-weight: 300;
                }}
                .header .date {{
                    margin-top: 10px;
                    font-size: 16px;
                    opacity: 0.9;
                }}
                .section {{
                    margin: 20px;
                }}
                .section-title {{
                    font-size: 22px;
                    font-weight: 600;
                    margin: 30px 0 20px 0;
                    padding: 15px;
                    border-radius: 8px;
                    display: flex;
                    align-items: center;
                }}
                .section-title.papers {{
                    background-color: #e3f2fd;
                    border-left: 5px solid #2196f3;
                    color: #1976d2;
                }}
                .section-title.news {{
                    background-color: #fff8e1;
                    border-left: 5px solid #ff9800;
                    color: #f57c00;
                }}
                .item {{
                    background-color: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 8px;
                    margin: 15px 0;
                    padding: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                    transition: box-shadow 0.3s ease;
                }}
                .item:hover {{
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                }}
                .item-title {{
                    font-size: 18px;
                    font-weight: 600;
                    margin-bottom: 12px;
                    color: #2c3e50;
                    line-height: 1.4;
                }}
                .item-meta {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 15px;
                    margin-bottom: 12px;
                    font-size: 14px;
                    color: #666;
                }}
                .meta-item {{
                    display: flex;
                    align-items: center;
                }}
                .meta-label {{
                    font-weight: 600;
                    margin-right: 5px;
                }}
                .abstract {{
                    color: #555;
                    line-height: 1.6;
                    margin-bottom: 15px;
                }}
                .link {{
                    display: inline-block;
                    background-color: #4CAF50;
                    color: white;
                    padding: 8px 16px;
                    text-decoration: none;
                    border-radius: 4px;
                    font-size: 14px;
                    transition: background-color 0.3s ease;
                }}
                .link:hover {{
                    background-color: #45a049;
                }}
                .news-link {{
                    background-color: #ff9800;
                }}
                .news-link:hover {{
                    background-color: #f57c00;
                }}
                .relevance-stars {{
                    color: #ffc107;
                    font-size: 16px;
                }}
                .stats {{
                    background-color: #f8f9fa;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 30px 20px;
                    text-align: center;
                }}
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
                    gap: 20px;
                    margin-top: 15px;
                }}
                .stat-item {{
                    text-align: center;
                }}
                .stat-number {{
                    font-size: 24px;
                    font-weight: 700;
                    color: #2196f3;
                }}
                .stat-label {{
                    font-size: 14px;
                    color: #666;
                    margin-top: 5px;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px;
                    color: #999;
                    font-size: 12px;
                    border-top: 1px solid #eee;
                }}
                .no-content {{
                    text-align: center;
                    padding: 40px;
                    color: #999;
                    font-style: italic;
                }}
                .emoji {{
                    margin-right: 8px;
                }}
                @media (max-width: 600px) {{
                    .container {{
                        margin: 10px;
                        border-radius: 5px;
                    }}
                    .header {{
                        padding: 20px;
                    }}
                    .header h1 {{
                        font-size: 24px;
                    }}
                    .section {{
                        margin: 15px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔬 数理最適化 日次レポート</h1>
                    <div class="date">{jst_now.strftime('%Y年%m月%d日 %H:%M')} JST</div>
                </div>
                
                <div class="section">
                    <div class="section-title papers">
                        <span class="emoji">📚</span>
                        新着論文 ({len(papers)}件)
                    </div>
        """
        
        # 論文セクション
        if papers:
            for i, paper in enumerate(papers, 1):
                authors_str = ', '.join(paper['authors'])
                if len(paper['authors']) > 3:
                    authors_str += " 他"
                
                categories_str = ', '.join(paper['categories'][:2])
                
                html_report += f"""
                    <div class="item">
                        <div class="item-title">{i}. {paper['title']}</div>
                        <div class="item-meta">
                            <div class="meta-item">
                                <span class="meta-label">👥 著者:</span>
                                {authors_str}
                            </div>
                            <div class="meta-item">
                                <span class="meta-label">🏷️ カテゴリ:</span>
                                {categories_str}
                            </div>
                            <div class="meta-item">
                                <span class="meta-label">📅 公開日:</span>
                                {paper['published']}
                            </div>
                        </div>
                        <div class="abstract">{paper['abstract']}</div>
                        <a href="{paper['url']}" class="link" target="_blank">論文を読む</a>
                    </div>
                """
        else:
            html_report += '<div class="no-content">本日は新着論文がありませんでした。</div>'
        
        # ニュースセクション
        html_report += f"""
                </div>
                
                <div class="section">
                    <div class="section-title news">
                        <span class="emoji">📰</span>
                        数理最適化関連技術ニュース ({len(news_items)}件)
                    </div>
        """
        
        if news_items:
            for i, news in enumerate(news_items, 1):
                stars = '⭐' * int(news['relevance_score'])
                
                html_report += f"""
                    <div class="item">
                        <div class="item-title">{i}. {news['title']}</div>
                        <div class="item-meta">
                            <div class="meta-item">
                                <span class="meta-label">🎯 関連度:</span>
                                <span class="relevance-stars">{stars}</span>
                            </div>
                            <div class="meta-item">
                                <span class="meta-label">📅 公開日:</span>
                                {news['published']}
                            </div>
                        </div>
                        <div class="abstract">{news['summary']}</div>
                        <a href="{news['link']}" class="link news-link" target="_blank">記事を読む</a>
                    </div>
                """
        else:
            html_report += '<div class="no-content">本日は関連ニュースがありませんでした。</div>'
        
        # 統計セクション
        html_report += f"""
                </div>
                
                <div class="stats">
                    <h3>📊 収集統計</h3>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-number">{len(papers)}</div>
                            <div class="stat-label">論文数</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number">{len(news_items)}</div>
                            <div class="stat-label">ニュース数</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number">{jst_now.strftime('%H:%M')}</div>
                            <div class="stat-label">生成時刻 (JST)</div>
                        </div>
                    </div>
                </div>
                
                <div class="footer">
                    このレポートは自動生成されました<br>
                    日本標準時 (JST) - {jst_now.strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_report
    
    def generate_text_report(self, papers, news_items):
        """テキスト版レポートを生成（Discord用など）"""
        jst_now = self.get_jst_time()
        
        report = f"""
# 🔬 数理最適化 日次レポート
**生成日時**: {jst_now.strftime('%Y年%m月%d日 %H:%M')} JST

---

## 📚 新着論文 ({len(papers)}件)

"""
        
        if papers:
            for i, paper in enumerate(papers, 1):
                authors_str = ', '.join(paper['authors'])
                if len(paper['authors']) > 3:
                    authors_str += " 他"
                
                report += f"""
### {i}. {paper['title']}

- **著者**: {authors_str}
- **カテゴリ**: {', '.join(paper['categories'][:2])}
- **公開日**: {paper['published']}
- **概要**: {paper['abstract']}
- **URL**: {paper['url']}

---
"""
        else:
            report += "\n本日は新着論文がありませんでした。\n\n---\n"
        
        report += f"""

## 📰 数理最適化関連技術ニュース ({len(news_items)}件)

"""
        
        if news_items:
            for i, news in enumerate(news_items, 1):
                report += f"""
### {i}. {news['title']}

- **要約**: {news['summary']}
- **関連度**: {'⭐' * int(news['relevance_score'])}
- **リンク**: {news['link']}
- **公開日**: {news['published']}

---
"""
        else:
            report += "\n本日は関連ニュースがありませんでした。\n\n---\n"
        
        report += f"""

## 📊 収集統計
- 論文数: {len(papers)}件
- ニュース数: {len(news_items)}件
- 生成時刻: {jst_now.strftime('%Y-%m-%d %H:%M:%S')} JST

---
*このレポートは自動生成されました (JST: Japan Standard Time)*
"""
        
        return report
    
    def send_email_report(self, html_report, text_report):
        """HTMLとテキスト両方に対応したメールを送信"""
        if not all([self.sender_email, self.sender_password, self.recipient_email]):
            print("❌ メール設定が不完全です")
            return False
        
        try:
            # マルチパートメッセージを作成
            msg = MIMEMultipart('alternative')
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            jst_now = self.get_jst_time()
            msg['Subject'] = f"🔬 数理最適化レポート - {jst_now.strftime('%Y/%m/%d')} JST"
            
            # テキスト版とHTML版の両方を添付
            text_part = MIMEText(text_report, 'plain', 'utf-8')
            html_part = MIMEText(html_report, 'html', 'utf-8')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # SMTP送信
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            text = msg.as_string()
            server.sendmail(self.sender_email, self.recipient_email, text)
            server.quit()
            
            print("✅ HTMLメールで送信完了")
            return True
            
        except Exception as e:
            print(f"❌ メール送信エラー: {e}")
            return False
    
    def send_discord_report(self, report):
        """Discord Webhookでレポートを送信"""
        if not self.discord_webhook:
            print("❌ Discord Webhook URLが設定されていません")
            return False
        
        try:
            # Discordの文字数制限（2000文字）対応
            if len(report) > 1900:
                report = report[:1900] + "\n\n[レポートが長いため切り詰められました]"
            
            payload = {
                "content": f"```markdown\n{report}\n```"
            }
            
            response = requests.post(self.discord_webhook, json=payload)
            if response.status_code == 204:
                print("✅ Discordに送信完了")
                return True
            else:
                print(f"❌ Discord送信エラー: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Discord送信エラー: {e}")
            return False
    
    def save_report_to_file(self, html_report, text_report):
        """レポートをファイルに保存（HTML版とテキスト版両方）"""
        jst_now = self.get_jst_time()
        timestamp = jst_now.strftime('%Y%m%d_%H%M')
        
        html_filename = f"report_{timestamp}_JST.html"
        text_filename = f"report_{timestamp}_JST.md"
        
        try:
            # HTML版を保存
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_report)
            print(f"✅ HTMLレポートを {html_filename} に保存しました")
            
            # テキスト版を保存
            with open(text_filename, 'w', encoding='utf-8') as f:
                f.write(text_report)
            print(f"✅ テキストレポートを {text_filename} に保存しました")
            
            return html_filename, text_filename
        except Exception as e:
            print(f"❌ ファイル保存エラー: {e}")
            return None, None
    
    def run_daily_collection(self):
        """日次収集とレポート生成を実行"""
        jst_now = self.get_jst_time()
        
        print("=" * 50)
        print(f"🚀 日次収集開始: {jst_now.strftime('%Y-%m-%d %H:%M:%S')} JST")
        print("=" * 50)

#        # テスト実行
#        test_success = self.simple_arxiv_test()
#        if not test_success:
#            print("⚠️ テストに失敗しましたが、本格収集を続行します...")

        
        # データ収集（修正版を使用）
        papers = self.collect_arxiv_papers_fixed(days_back=2)  # 2日分
#        news_items = self.collect_news_from_rss()
        news_items = self.collect_news_from_rss_improved()
        
        # レポート生成（HTML版とテキスト版）
        html_report = self.generate_html_report(papers, news_items)
        text_report = self.generate_text_report(papers, news_items)
        
        # レポート保存
        self.save_report_to_file(html_report, text_report)
        
        # レポート送信
        email_sent = self.send_email_report(html_report, text_report)
        
        print("=" * 50)
        print("📊 実行結果:")
        print(f"  📚 論文: {len(papers)}件")
        print(f"  📰 ニュース: {len(news_items)}件")
        print(f"  📧 HTMLメール送信: {'✅' if email_sent else '❌'}")
        print(f"  🕐 実行時刻: {jst_now.strftime('%Y-%m-%d %H:%M:%S')} JST")
        print("=" * 50)
        
        return {
            'papers_count': len(papers),
            'news_count': len(news_items),
            'email_sent': email_sent,
            'execution_time_jst': jst_now.strftime('%Y-%m-%d %H:%M:%S JST')
        }

def main():
    """メイン実行関数"""
    print("🔬 数理最適化論文・ニュース収集システム")
    print("=" * 60)

    collector = OptimizationNewsCollector()
    result = collector.run_daily_collection()
    
    # 結果をJSONで出力（GitHub Actionsでの確認用）
    print("\n📄 実行結果（JSON）:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
