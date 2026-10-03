"""Optional: pip install playwright && playwright install chromium."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import requests
from playwright.sync_api import sync_playwright, expect


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    proc = subprocess.Popen([sys.executable, '-m', 'manager.server', '--demo', '--port', str(port)], env={**{k:v for k,v in os.environ.items() if k != 'MANAGER_TOKEN'}, 'JASMIN_GATEWAYS':'production,test', 'JASMIN_DEFAULT_GATEWAY':'production'}, stdout=subprocess.DEVNULL)
    url = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try: requests.get(url, timeout=.2); break
            except requests.ConnectionError: time.sleep(.05)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width':1440, 'height':1080})
            errors=[]
            page.on('pageerror',lambda error: errors.append(str(error)))
            page.goto(url)
            expect(page.locator('#mode')).to_have_text('Demo workspace')
            modal=page.locator('#modal')
            def create(kind, values):
                page.locator(f'[data-create="{kind}"]').first.click()
                for key,value in values.items():
                    field=modal.locator(f'[name="{key}"]')
                    if field.evaluate('(e)=>e.tagName')=='SELECT': field.select_option(str(value))
                    else:field.fill(str(value))
                modal.locator('[type="submit"]').click()
                expect(modal).not_to_be_visible()
            create('groups',{'gid':'customers'})
            create('users',{'uid':'app01','gid':'customers','username':'notifications','password':'secret','balance':'250'})
            page.locator('nav [data-page="connectors"]').click()
            create('connectors',{'id':'primary','host':'smsc.example.com','username':'system01','password':'secret','throughput':'50'})
            page.locator('[data-op="start"]').click()
            expect(page.locator('tbody')).to_contain_text('BOUND_TRX')
            page.locator('nav [data-page="users"]').click()
            page.locator('[data-op="quotas"]').click()
            modal.locator('[name="balance"]').fill('500')
            modal.locator('[type="submit"]').click()
            expect(modal).not_to_be_visible()
            expect(page.locator('tbody')).to_contain_text('500')
            page.locator('[data-op="edit"]').click()
            modal.locator('[name="username"]').fill('updatedname')
            modal.locator('[type="submit"]').click()
            expect(modal).not_to_be_visible()
            expect(page.locator('tbody')).to_contain_text('updatedname')
            page.locator('nav [data-page="connectors"]').click()
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('[data-op="stop"]').click()
            expect(page.locator('[data-op="start"]')).to_be_visible()
            page.locator('[data-op="edit"]').click()
            modal.locator('[name="host"]').fill('edited.example.com')
            modal.locator('[type="submit"]').click()
            expect(modal).not_to_be_visible()
            expect(page.locator('tbody')).to_contain_text('edited.example.com')
            page.locator('nav [data-page="mt"]').click()
            create('mt',{'type':'Default','order':'0','destination':'primary','rate':'.02'})
            expect(page.locator('tbody')).to_contain_text('DefaultRoute')
            page.locator('nav [data-page="mo"]').click()
            create('mo',{'type':'Static','order':'10','destination':'webhook','url':'https://example.com/inbound','filterType':'Connector','filterValue':'primary'})
            expect(page.locator('tbody')).to_contain_text('StaticMORoute')
            page.locator('nav [data-page="mt_interceptors"]').click()
            create('mt_interceptors',{'type':'Static','order':'20','filterType':'User','filterValue':'app01','script':'routable.addTag(123)\n'})
            expect(page.locator('tbody')).to_contain_text('StaticMTInterceptor')
            page.locator('[data-interceptor-edit]').click()
            expect(modal.locator('[name="script"]')).to_have_value('routable.addTag(123)\n')
            modal.locator('[name="script"]').fill('routable.addTag(456)\n')
            modal.locator('[type="submit"]').click()
            expect(modal).not_to_be_visible()
            expect(page.locator('tbody')).to_contain_text('456')
            page.locator('nav [data-page="mo_interceptors"]').click()
            create('mo_interceptors',{'type':'Default','script':'smpp_status = 0\n'})
            expect(page.locator('tbody')).to_contain_text('DefaultInterceptor')
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('#flush-interceptors').click()
            expect(page.locator('#content')).to_contain_text('No interceptors configured')
            page.locator('nav [data-page="mt"]').click()
            page.locator('[data-create="mt"]').click()
            modal.locator('[name="filterType"]').select_option('Existing')
            expect(modal.locator('[name="filterValue"]')).to_have_js_property('tagName','SELECT')
            modal.locator('[name="filterValue"]').select_option(index=1)
            modal.locator('[name="order"]').fill('100')
            modal.locator('[type="submit"]').click()
            expect(modal).not_to_be_visible()
            page.get_by_role('button',name='Order',exact=True).click()
            expect(page.locator('tbody tr').first.locator('td').first).to_have_text('0')
            page.get_by_role('button',name='Order',exact=True).click()
            expect(page.locator('tbody tr').first.locator('td').first).to_have_text('100')
            page.locator('#save').click()
            expect(page.locator('#toast')).to_contain_text('marked saved')
            page.locator('nav [data-page="overview"]').click()
            expect(page.locator('#content')).to_contain_text('Saved')
            page.locator('#toast').evaluate('(e)=>e.hidden=true')
            page.mouse.move(1200, 100)
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/dashboard.png',full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path='artifacts/mobile.png',full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
            page.set_viewport_size({'width':1440,'height':1080})
            page.locator('#gateway-select').select_option('test')
            expect(page.locator('#connection-label')).to_have_text('Demo gateway · simulated')
            expect(page.locator('.stat-value').first).to_have_text('0')
            create('groups',{'gid':'test_only'})
            page.reload()
            expect(page.locator('#gateway-select')).to_have_value('test')
            expect(page.locator('.stat-value').first).to_have_text('0')
            page.locator('#gateway-select').select_option('production')
            expect(page.locator('.stat-value').first).to_have_text('1')
            # Hold a production refresh response while switching to the test gateway.
            page.evaluate('''() => {
                const original=window.fetch;
                window.fetch=async (...args)=>{
                    const response=await original(...args);
                    if(String(args[0]).endsWith('/api/state') && args[1].headers['X-Jasmin-Gateway']==='production'){
                        await new Promise(resolve=>window.releaseOldGateway=resolve);
                    }
                    return response;
                };
            }''')
            page.locator('#refresh').click()
            page.wait_for_function('typeof window.releaseOldGateway === "function"')
            page.locator('#gateway-select').select_option('test')
            expect(page.locator('.stat-value').first).to_have_text('0')
            page.evaluate('window.releaseOldGateway()')
            page.wait_for_function('document.querySelector("#refresh").disabled === false')
            expect(page.locator('#gateway-select')).to_have_value('test')
            expect(page.locator('.stat-value').first).to_have_text('0')
            assert not errors, errors
            browser.close()
            print('Browser smoke passed: group/user/connector, bind control, quota update, MT/MO creation, persistence, responsive layout.')
    finally:
        proc.terminate();proc.wait(timeout=5)


if __name__=='__main__':main()
