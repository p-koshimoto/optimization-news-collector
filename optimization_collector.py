import arxiv
import feedparser
import requests
from datetime import datetime, timedelta
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import sys

class OptimizationNewsCollector:
    def __init__(self):
        # 環境変数からメール設定を取得
        self.recipient_email = os.getenv('RECIPIENT_EMAIL')
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('GMAIL_APP_PASSWORD')
        
        # 設定チェック
        if not all([self.recipient_email, self.sender_email, self.sender_password]):
            print("❌ メール設定が不完全です。GitHub Secretsを確認してください。")
            print(f"   RECIPIENT_EMAIL: {'✅' if self.recipient_email else '❌'}")
            print(f"   SENDER_EMAIL: {'✅' if self.sender_email else '❌'}")
            print(f"   GMAIL_APP_PASSWORD: {'✅' if self.sender_password else '❌'}")
        
    def collect_arxiv_papers(self, days_back=1):
        """arXivから数理最適化関連論文を収集"""
        print("📚 arXivから論文を収集中...")
        
        try:
            # 数理最適化関連のカテゴリで検索
            client = arxiv.Client()
            search = arxiv.Search(
                query="cat:math.OC OR cat:cs.DM OR ti:optimization OR ti:programming",
                max_results=20,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            papers = []
            for result in client.results(search):
                # 過去N日以内の論文のみ
                if (datetime.now().date() - result.published.date()).days <= days_back:
                    papers.append({
                        'title': result.title.replace('\n', ' ').strip(),
                        'authors': [author.name for author in result.authors[:3]],  # 最初の3名
                        'abstract': result.summary.replace('\n', ' ').strip()[:500] + "...",
                        'url': result.entry_id,
                        'published': result.published.strftime('%Y-%m-%d'),
                        'categories': result.categories
                    })
            
            print(f"✅ 論文 {len(papers)} 件を収集しました")
            return papers
            
        except Exception as e:
            print(f"❌ arXiv収集エラー: {e}")
            return []
    
    def collect_news_from_rss(self):
        """RSSから最適化関連ニュースを収集"""
        print("📰 ニュースを収集中...")
        
        # 複数のRSSソースを使用（技術系に絞る）
        rss_urls = [
            "https://rss.cnn.com/rss/edition_technology.rss",
            "https://feeds.reuters.com/reuters/technologyNews",
            "https://rss.slashdot.org/Slashdot/slashdotMain"
        ]
        
        news_items = []
        for rss_url in rss_urls:
            try:
                feed = feedparser.parse(rss_url)
                for entry in feed.entries[:5]:  # 各RSSから5件
                    # 最適化・AI関連キーワードでフィルタ
                    title_lower = entry.title.lower()
                    summary_lower = getattr(entry, 'summary', '').lower()
                    content = (title_lower + ' ' + summary_lower)
                    
                    if any(keyword in content for keyword in [
                        'optimization', 'algorithm', 'ai', 'machine learning', 
                        'data science', 'research', 'mathematical', 'computing'
                    ]):
                        news_items.append({
                            'title': entry.title,
                            'link': entry.link,
                            'published': getattr(entry, 'published', ''),
                            'summary': getattr(entry, 'summary', '')[:400] + "..."
                        })
            except Exception as e:
                print(f"⚠️ RSS取得エラー ({rss_url}): {e}")
                continue
        
        print(f"✅ ニュース {len(news_items)} 件を収集しました")
        return news_items
    
    def generate_html_report(self, papers, news_items):
        """HTMLメール用のレポートを生成"""
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
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            border-bottom: 3px solid #007acc;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #007acc;
            margin: 0;
            font-size: 28px;
        }}
        .date {{
            color: #666;
            font-size: 14px;
            margin-top: 10px;
        }}
        .section {{
            margin-bottom: 40px;
        }}
        .section h2 {{
            color: #007acc;
            border-left: 4px solid #007acc;
            padding-left: 15px;
            font-size: 20px;
        }}
        .item {{
            background-color: #f9f9f9;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
            border-left: 4px solid #28a745;
        }}
        .paper-item {{
            border-left-color: #007acc;
        }}
        .news-item {{
            border-left-color: #ffc107;
        }}
        .item h3 {{
            margin-top: 0;
            color: #333;
            font-size: 16px;
        }}
        .meta {{
            color: #666;
            font-size: 12px;
            margin-bottom: 10px;
        }}
        .abstract {{
            margin: 10px 0;
            color: #555;
        }}
        .url {{
            margin-top: 10px;
        }}
        .url a {{
            color: #007acc;
            text-decoration: none;
        }}
        .url a:hover {{
            text-decoration: underline;
        }}
        .stats {{
            background-color: #e9ecef;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            margin-top: 30px;
        }}
        .no-items {{
            text-align: center;
            color: #666;
            font-style: italic;
            padding: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔬 数理最適化 日次レポート</h1>
            <div class="date">生成日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</div>
        </div>
        
        <div class="section">
            <h2>📚 新着論文 ({len(papers)}件)</h2>
"""
        
        if papers:
            for i, paper in enumerate(papers, 1):
                authors_str = ', '.join(paper['authors'])
                if len(paper['authors']) > 3:
                    authors_str += " 他"
                
                html_report += f"""
            <div class="item paper-item">
                <h3>{i}. {paper['title']}</h3>
                <div class="meta">
                    <strong>著者:</strong> {authors_str} | 
                    <strong>カテゴリ:</strong> {', '.join(paper['categories'][:2])} | 
                    <strong>公開日:</strong> {paper['published']}
                </div>
                <div class="abstract">{paper['abstract']}</div>
                <div class="url"><a href="{paper['url']}" target="_blank">論文を見る →</a></div>
            </div>
"""
        else:
            html_report += '<div class="no-items">本日は新着論文がありませんでした。</div>'
        
        html_report += f"""
        </div>
        
        <div class="section">
            <h2>📰 関連技術ニュース ({len(news_items)}件)</h2>
"""
        
        if news_items:
            for i, news in enumerate(news_items, 1):
                html_report += f"""
            <div class="item news-item">
                <h3>{i}. {news['title']}</h3>
                <div class="meta">
                    <strong>公開日:</strong> {news['published']}
                </div>
                <div class="abstract">{news['summary']}</div>
                <div class="url"><a href="{news['link']}" target="_blank">記事を読む →</a></div>
            </div>
"""
        else:
            html_report += '<div class="no-items">本日は関連ニュースがありませんでした。</div>'
        
        html_report += f"""
        </div>
        
        <div class="stats">
            <strong>📊 収集統計</strong><br>
            論文数: {len(papers)}件 | ニュース数: {len(news_items)}件<br>
            生成時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
            <em>このレポートは自動生成されました</em>
        </div>
    </div>
</body>
</html>
"""
        
        return html_report
    
    def generate_text_report(self, papers, news_items):
        """テキスト版レポートを生成（HTMLメール非対応環境用）"""
        report = f"""
🔬 数理最適化 日次レポート
生成日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📚 新着論文 ({len(papers)}件)

"""
        
        if papers:
            for i, paper in enumerate(papers, 1):
                authors_str = ', '.join(paper['authors'])
                if len(paper['authors']) > 3:
                    authors_str += " 他"
                
                report += f"""
{i}. {paper['title']}

著者: {authors_str}
カテゴリ: {', '.join(paper['categories'][:2])}
公開日: {paper['published']}
概要: {paper['abstract']}
URL: {paper['url']}

{'-' * 60}
"""
        else:
            report += "\n本日は新着論文がありませんでした。\n\n"
        
        report += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📰 関連技術ニュース ({len(news_items)}件)

"""
        
        if news_items:
            for i, news in enumerate(news_items, 1):
                report += f"""
{i}. {news['title']}

要約: {news['summary']}
リンク: {news['link']}
公開日: {news['published']}

{'-' * 60}
"""
        else:
            report += "\n本日は関連ニュースがありませんでした。\n\n"
        
        report += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 収集統計
論文数: {len(papers)}件
ニュース数: {len(news_items)}件
生成時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

このレポートは自動生成されました
"""
        
        return report
    
    def send_email_report(self, html_report, text_report):
        """Gmailでレポートを送信（HTMLとテキスト両方）"""
        if not all([self.sender_email, self.sender_password, self.recipient_email]):
            print("❌ メール設定が不完全です")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            msg['Subject'] = f"🔬 数理最適化レポート - {datetime.now().strftime('%Y/%m/%d')}"
            
            # テキスト版とHTML版の両方を添付
            part1 = MIMEText(text_report, 'plain', 'utf-8')
            part2 = MIMEText(html_report, 'html', 'utf-8')
            
            msg.attach(part1)
            msg.attach(part2)
            
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
    
    def save_report_to_file(self, text_report, html_report):
        """レポートをファイルに保存"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        
        # テキスト版保存
        text_filename = f"report_{timestamp}.md"
        try:
            with open(text_filename, 'w', encoding='utf-8') as f:
                f.write(text_report)
            print(f"✅ テキストレポートを {text_filename} に保存しました")
        except Exception as e:
            print(f"❌ テキストファイル保存エラー: {e}")
        
        # HTML版保存
        html_filename = f"report_{timestamp}.html"
        try:
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_report)
            print(f"✅ HTMLレポートを {html_filename} に保存しました")
        except Exception as e:
            print(f"❌ HTMLファイル保存エラー: {e}")
        
        return text_filename, html_filename
    
    def run_daily_collection(self):
        """日次収集とレポート生成を実行"""
        print("=" * 60)
        print(f"🚀 数理最適化論文・ニュース収集開始")
        print(f"   実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # データ収集
        papers = self.collect_arxiv_papers(days_back=2)  # 過去2日分
        news_items = self.collect_news_from_rss()
        
        # レポート生成
        html_report = self.generate_html_report(papers, news_items)
        text_report = self.generate_text_report(papers, news_items)
        
        # レポート保存
        self.save_report_to_file(text_report, html_report)
        
        # メール送信
        email_sent = self.send_email_report(html_report, text_report)
        
        print("=" * 60)
        print("📊 実行結果:")
        print(f"  📚 論文: {len(papers)}件")
        print(f"  📰 ニュース: {len(news_items)}件")
        print(f"  📧 メール送信: {'✅ 成功' if email_sent else '❌ 失敗'}")
        print("=" * 60)
        
        return {
            'papers_count': len(papers),
            'news_count': len(news_items),
            'email_sent': email_sent,
            'execution_time': datetime.now().isoformat()
        }

def main():
    """メイン実行関数"""
    print("🔬 数理最適化論文・ニュース収集システム")
    print("   Version: 1.0 (Email-only)")
    print("=" * 60)
    
    collector = OptimizationNewsCollector()
    result = collector.run_daily_collection()
    
    # 結果をJSONで出力（GitHub Actionsでの確認用）
    print("\n📄 実行結果（JSON）:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 実行結果に応じて終了コードを設定
    if result['email_sent']:
        print("\n🎉 全処理が正常に完了しました！")
        sys.exit(0)
    else:
        print("\n⚠️ 一部処理でエラーが発生しました")
        sys.exit(1)

if __name__ == "__main__":
    main()
