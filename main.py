import sys
import requests
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QTableWidget, 
                             QTableWidgetItem, QLabel, QProgressBar, QMessageBox,
                             QHeaderView, QComboBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re


class ParserThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, url, sort_by, product_type):
        super().__init__()
        self.url = url
        self.sort_by = sort_by
        self.product_type = product_type

    def run(self):
        try:
            self.progress.emit(10)
            products = self.parse_page(self.url)
            self.progress.emit(80)
            
            if products:
                if self.sort_by == "Продажи (убывание)":
                    products.sort(key=lambda x: x['sales'], reverse=True)
                elif self.sort_by == "Цена (возрастание)":
                    products.sort(key=lambda x: x['price'])
                elif self.sort_by == "Цена (убывание)":
                    products.sort(key=lambda x: x['price'], reverse=True)
                
                self.progress.emit(100)
                self.finished.emit(products)
            else:
                self.error.emit("Не удалось извлечь товары с данной страницы")
        except Exception as e:
            self.error.emit(f"Ошибка парсинга: {str(e)}")

    def parse_page(self, url):
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        try:
            driver = webdriver.Chrome(options=options)
        except:
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            except:
                self.error.emit("Не удалось инициализировать Chrome WebDriver. Установите ChromeDriver вручную.")
                return []
        
        try:
            driver.get(url)
            time.sleep(3)
            
            is_ggsel_main = url.rstrip('/') == 'https://ggsel.net'
            
            if is_ggsel_main:
                try:
                    from selenium.webdriver.common.by import By
                    
                    time.sleep(2)
                    
                    next_buttons = driver.find_elements(By.CSS_SELECTOR, 
                        'button[aria-label="Next slide"], button.swiper-button-next, button[class*="next"]')
                    
                    if next_buttons:
                        max_clicks = 15
                        clicks_done = 0
                        
                        for i in range(max_clicks):
                            try:
                                active_next = None
                                for btn in next_buttons:
                                    try:
                                        if btn.is_displayed() and btn.is_enabled():
                                            classes = btn.get_attribute('class') or ''
                                            if 'disabled' not in classes.lower():
                                                active_next = btn
                                                break
                                    except:
                                        continue
                                
                                if not active_next:
                                    print(f"Слайдер прокручен до конца ({clicks_done} кликов)")
                                    break

                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", active_next)
                                time.sleep(0.3)
                                driver.execute_script("arguments[0].click();", active_next)
                                clicks_done += 1
                                time.sleep(0.5)

                                next_buttons = driver.find_elements(By.CSS_SELECTOR, 
                                    'button[aria-label="Next slide"], button.swiper-button-next, button[class*="next"]')
                                
                            except Exception as e:
                                print(f"Прокрутка завершена: {e}")
                                break
                        
                        time.sleep(2)
                    
                except Exception as e:
                    print(f"Ошибка при прокрутке слайдера: {e}")
            else:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            if 'ggsel' in url:
                return self.parse_ggsel(soup, url)
            elif 'plati' in url:
                return self.parse_plati(soup, url)
            else:
                return self.parse_generic(soup, url)
        finally:
            driver.quit()


    def parse_ggsel(self, soup, base_url):
        """Улучшенный парсинг с лучшей обработкой главной страницы"""
        products = []

        is_main_page = base_url.rstrip('/') == 'https://ggsel.net'

        items = soup.find_all('div', {'class': 'ProductCard_card__zjTV_'})
        
        for item in items[:100]:
            try:
                category_elem = item.find('div', {'data-testid': 'card-category'})
                category = category_elem.get_text(strip=True) if category_elem else ''

                if self.product_type != "Все":
                    if category != self.product_type:
                        continue

                name_elem = item.find('span', {'class': 'ProductCard_description__AXXxp'})
                if not name_elem:
                    name_elem = item.find('div', {'data-testid': 'card-description'})

                price_elem = item.find('div', {'data-testid': 'card-price'})
                if not price_elem:
                    price_elem = item.find('span', {'class': 'ProductCard_price__k1Ahq'})

                sales_elem = item.find('div', {'data-testid': 'card-counter'})

                link_elem = item.find('a', {'data-testid': 'card-link'})
                if not link_elem:
                    link_elem = item.find('a', {'data-testid': 'card-button'})
                
                if name_elem and price_elem:
                    title = name_elem.get_text(strip=True)
                    
                    price_text = price_elem.get_text(strip=True)

                    if '=' in price_text:
                        price_text = price_text.split('=')[-1].strip()
                    
                    price_clean = price_text.replace('₽', '').replace('\xa0', '').replace(' ', '').strip()
                    
                    try:
                        price = float(price_clean)
                    except:
                        continue
                    
                    sales = 0
                    if sales_elem:
                        sales_text = sales_elem.get_text(strip=True)
                        sales_text = sales_text.replace('\xa0', '').replace(' ', '')
                        
                        if '+' in sales_text:
                            sales_match = re.search(r'(\d+)\+', sales_text)
                            if sales_match:
                                sales = int(sales_match.group(1))
                        else:
                            sales_match = re.search(r'(\d+)', sales_text)
                            if sales_match:
                                sales = int(sales_match.group(1))
                    
                    link = ''
                    if link_elem and link_elem.get('href'):
                        link = link_elem['href']
                        if not link.startswith('http'):
                            link = 'https://ggsel.net' + link
                    
                    products.append({
                        'name': title,
                        'price': price,
                        'sales': sales,
                        'link': link,
                        'category': category
                    })
            except Exception as e:
                continue
        
        return products


    def parse_plati(self, soup, base_url):
        products = []

        top_sellers = soup.find('ul', id='top-sellers')
        if not top_sellers:
            sections = soup.find_all('section', class_='content')
            for sec in sections:
                if 'Лидеры продаж' in sec.get_text():
                    top_sellers = sec.find('ul', class_='section-list')
                    break
        
        if not top_sellers:
            cards = soup.find_all('a', class_='card')
        else:
            cards = top_sellers.find_all('a', class_='card')
        
        for card in cards[:50]:
            try:
                if 'd-none' in card.parent.get('class', []):
                    continue

                title_span = card.find('span', class_='footnote-medium')
                if not title_span:
                    title_p = card.find('p', class_='custom-link')
                    if title_p:
                        title_span = title_p.find('span', class_='footnote-medium')
                title = title_span.get_text(strip=True) if title_span else ''
                if not title:
                    continue

                price_span = card.find('span', class_='title-bold')
                if not price_span:
                    continue
                price_text = price_span.get_text(strip=True)
                price_clean = re.sub(r'[^\d.]', '', price_text.replace(',', '.'))
                try:
                    price = float(price_clean)
                except:
                    continue
                
                sales = 0
                sold_span = card.find('span', class_='footnote-regular')
                if sold_span:
                    sold_text = sold_span.get_text(strip=True)
                    sold_text = sold_text.replace('\xa0', '').replace(' ', '')
                    
                    if 'млн' in sold_text:
                        m = re.search(r'(\d+(?:\.\d+)?)', sold_text)
                        if m:
                            sales = int(float(m.group(1)) * 1_000_000)
                    elif 'тыс' in sold_text or 'k' in sold_text.lower():
                        m = re.search(r'(\d+(?:\.\d+)?)', sold_text)
                        if m:
                            sales = int(float(m.group(1)) * 1_000)
                    elif '+' in sold_text:
                        m = re.search(r'(\d+)', sold_text)
                        if m:
                            sales = int(m.group(1))
                    else:
                        m = re.search(r'(\d+)', sold_text)
                        if m:
                            sales = int(m.group(1))
                    if 'менее' in sold_text.lower():
                        sales = 5

                link = card.get('href', '')
                if link and not link.startswith('http'):
                    link = 'https://plati.market' + link
                
                products.append({
                    'name': title,
                    'price': price,
                    'sales': sales,
                    'link': link,
                    'category': ''
                })
                
            except Exception as e:
                print(f"Ошибка парсинга карточки: {e}")
                continue
        
        return products

    def parse_generic(self, soup, base_url):
        products = []
        
        patterns = [
            {'container': re.compile(r'product|item|card|goods|offer'), 
             'title': re.compile(r'title|name|product|heading'),
             'price': re.compile(r'price|cost|sum|rub'),
             'sales': re.compile(r'sold|sales|продаж|купили')},
        ]
        
        for pattern in patterns:
            items = soup.find_all(['div', 'article', 'li', 'section'], class_=pattern['container'])
            
            for item in items[:50]:
                try:
                    title_elem = item.find(['h1', 'h2', 'h3', 'h4', 'a', 'span', 'div'], 
                                          class_=pattern['title'])
                    price_elem = item.find(['span', 'div', 'p', 'strong'], 
                                          class_=pattern['price'])
                    sales_elem = item.find(['span', 'div'], 
                                          text=re.compile(r'\d+\s*(продаж|sold|sales)', re.I))
                    link_elem = item.find('a', href=True)
                    
                    if title_elem and price_elem:
                        title = title_elem.get_text(strip=True)
                        price_text = price_elem.get_text(strip=True)
                        price_match = re.search(r'[\d\s]+[.,]?\d*', price_text)
                        if price_match:
                            price = float(re.sub(r'[^\d.]', '', price_match.group().replace(',', '.')))
                        else:
                            continue
                        
                        sales = 0
                        if sales_elem:
                            sales_text = sales_elem.get_text(strip=True)
                            sales_match = re.search(r'(\d+)', sales_text)
                            if sales_match:
                                sales = int(sales_match.group(1))
                        
                        link = link_elem['href'] if link_elem else ''
                        if link and not link.startswith('http'):
                            if link.startswith('/'):
                                link = base_url.split('/')[0] + '//' + base_url.split('/')[2] + link
                            else:
                                link = base_url.rsplit('/', 1)[0] + '/' + link
                        
                        products.append({
                            'name': title[:100],
                            'price': price,
                            'sales': sales,
                            'link': link
                        })
                except:
                    continue
            
            if products:
                break
        
        return products


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Анализатор популярности товаров")
        self.setGeometry(0, 0, 1920, 1080)
        
        self.setup_ui()
        
    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        main_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f8f9fa, stop:1 #e9ecef);
            }
        """)
        
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        title_container = QWidget()
        title_container.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 12px;
                padding: 20px;
            }
        """)
        title_layout = QVBoxLayout(title_container)
        
        title = QLabel("📊 Анализатор популярности товаров")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: white; background: transparent;")
        title_layout.addWidget(title)
        
        layout.addWidget(title_container)

        url_container = QWidget()
        url_container.setStyleSheet("""
            QWidget {
                background-color: white;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        url_layout = QHBoxLayout(url_container)
        url_layout.setSpacing(10)
        
        url_label = QLabel("🔗 URL:")
        url_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        url_label.setStyleSheet("color: #495057; background: transparent;")
        url_layout.addWidget(url_label)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Введите ссылку на страницу с товарами (например: https://ggsel.net)")
        self.url_input.setFont(QFont("Segoe UI", 11))
        self.url_input.setStyleSheet("""
            QLineEdit {
                padding: 12px 15px;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                background-color: #f8f9fa;
                color: #212529;
            }
            QLineEdit:focus {
                border: 2px solid #667eea;
                background-color: white;
            }
        """)
        self.url_input.setMinimumHeight(45)
        url_layout.addWidget(self.url_input)
        
        layout.addWidget(url_container)

        controls_container = QWidget()
        controls_container.setStyleSheet("""
            QWidget {
                background-color: white;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        controls_layout = QHBoxLayout(controls_container)
        controls_layout.setSpacing(15)
 
        sort_label = QLabel("📋 Сортировка:")
        sort_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        sort_label.setStyleSheet("color: #495057; background: transparent;")
        controls_layout.addWidget(sort_label)
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Продажи (убывание)", "Цена (возрастание)", "Цена (убывание)"])
        self.sort_combo.setFont(QFont("Segoe UI", 11))
        self.sort_combo.setStyleSheet("""
            QComboBox {
                padding: 10px 15px;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                background-color: #f8f9fa;
                color: #212529;
                min-width: 200px;
            }
            QComboBox:hover {
                border: 2px solid #667eea;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
            QComboBox QAbstractItemView {
                border: 2px solid #dee2e6;
                border-radius: 8px;
                background-color: white;
                selection-background-color: #667eea;
                selection-color: white;
            }
        """)
        self.sort_combo.setMinimumHeight(45)
        controls_layout.addWidget(self.sort_combo)

        type_label = QLabel("🏷️ Тип:")
        type_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        type_label.setStyleSheet("color: #495057; background: transparent;")
        controls_layout.addWidget(type_label)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Все", "Ключ", "Гифт", "DLC", "Пополнение"])
        self.type_combo.setFont(QFont("Segoe UI", 11))
        self.type_combo.setStyleSheet("""
            QComboBox {
                padding: 10px 15px;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                background-color: #f8f9fa;
                color: #212529;
                min-width: 150px;
            }
            QComboBox:hover {
                border: 2px solid #667eea;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
            QComboBox QAbstractItemView {
                border: 2px solid #dee2e6;
                border-radius: 8px;
                background-color: white;
                selection-background-color: #667eea;
                selection-color: white;
            }
        """)
        self.type_combo.setMinimumHeight(45)
        controls_layout.addWidget(self.type_combo)
        
        controls_layout.addStretch()

        self.parse_button = QPushButton("🚀 НАЧАТЬ АНАЛИЗ")
        self.parse_button.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.parse_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                padding: 12px 30px;
                border: none;
                border-radius: 10px;
                min-width: 200px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5568d3, stop:1 #6a3f8f);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a5ab8, stop:1 #5d3679);
            }
            QPushButton:disabled {
                background: #adb5bd;
            }
        """)
        self.parse_button.setMinimumHeight(50)
        self.parse_button.clicked.connect(self.start_parsing)
        controls_layout.addWidget(self.parse_button)
        
        layout.addWidget(controls_container)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 8px;
                text-align: center;
                background-color: #e9ecef;
                color: #495057;
                font-weight: bold;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 8px;
            }
        """)
        self.progress_bar.setMinimumHeight(30)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("✅ Готов к работе")
        self.status_label.setFont(QFont("Segoe UI", 11))
        self.status_label.setStyleSheet("color: #495057; padding: 5px; background: transparent;")
        layout.addWidget(self.status_label)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Название товара", "Категория", "Цена (₽)", "Продажи", "Ссылка"])
        self.table.setFont(QFont("Segoe UI", 10))
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        
        self.table.setStyleSheet("""
            QTableWidget {
                border: none;
                border-radius: 12px;
                background-color: white;
                gridline-color: #e9ecef;
                alternate-background-color: white;
            }
            QTableWidget::item {
                padding: 10px;
                color: #212529;
                background-color: white;
            }
            QTableWidget::item:selected {
                background-color: #667eea;
                color: white;
            }
            QHeaderView::section {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #495057, stop:1 #343a40);
                color: white;
                padding: 12px;
                border: none;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        layout.addWidget(self.table)

        self.results_label = QLabel("📦 Результатов: 0")
        self.results_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.results_label.setStyleSheet("color: #495057; padding: 10px; background: transparent;")
        layout.addWidget(self.results_label)

    def start_parsing(self):
        url = self.url_input.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Ошибка", "Введите URL страницы")
            return
        
        if not url.startswith('http'):
            QMessageBox.warning(self, "Ошибка", "URL должен начинаться с http:// или https://")
            return
        
        self.parse_button.setEnabled(False)
        self.table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.status_label.setText("⏳ Загрузка страницы и анализ товаров...")
        self.status_label.setStyleSheet("color: #667eea; font-weight: bold; background: transparent;")
        
        self.parser_thread = ParserThread(url, self.sort_combo.currentText(), self.type_combo.currentText())
        self.parser_thread.progress.connect(self.update_progress)
        self.parser_thread.finished.connect(self.show_results)
        self.parser_thread.error.connect(self.show_error)
        self.parser_thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def show_results(self, products):
        self.table.setRowCount(len(products))
        
        for i, product in enumerate(products):
            name_item = QTableWidgetItem(product['name'])
            name_item.setFont(QFont("Arial", 11))
            self.table.setItem(i, 0, name_item)
            
            category_item = QTableWidgetItem(product.get('category', ''))
            category_item.setFont(QFont("Arial", 11))
            category_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 1, category_item)
            
            price_item = QTableWidgetItem(f"{product['price']:.2f}")
            price_item.setFont(QFont("Arial", 11))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 2, price_item)
            
            sales_item = QTableWidgetItem(str(product['sales']))
            sales_item.setFont(QFont("Arial", 11, QFont.Weight.Bold))
            sales_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if product['sales'] > 100:
                sales_item.setForeground(QColor("#27ae60"))
            elif product['sales'] > 50:
                sales_item.setForeground(QColor("#f39c12"))
            else:
                sales_item.setForeground(QColor("#95a5a6"))
            self.table.setItem(i, 3, sales_item)
            
            link_item = QTableWidgetItem(product['link'])
            link_item.setFont(QFont("Arial", 10))
            link_item.setForeground(QColor("#3498db"))
            self.table.setItem(i, 4, link_item)
        
        self.results_label.setText(f"Результатов: {len(products)}")
        self.status_label.setText("✅ Анализ завершен успешно!")
        self.status_label.setStyleSheet("color: #28a745; font-weight: bold; background: transparent;")
        self.progress_bar.setValue(100)
        self.parse_button.setEnabled(True)

    def show_error(self, error_msg):
        self.status_label.setText(f"❌ Ошибка: {error_msg}")
        self.status_label.setStyleSheet("color: #dc3545; font-weight: bold; background: transparent;")
        self.progress_bar.setValue(0)
        self.parse_button.setEnabled(True)
        QMessageBox.critical(self, "Ошибка", error_msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 245))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(44, 62, 80))
    app.setPalette(palette)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())