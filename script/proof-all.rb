require 'html-proofer'

options = { 
    :url_ignore => [/localhost:4000/],
    :log_level => :info,
    :assume_extension => true ,
    :external_only => true,
    :check_sri => true,
    :check_html => true,
    :check_img_http => true,
    :check_opengraph => true,
    :enforce_https => true,
    :cache => {
      :timeframe => '1w'
    },
    :typhoeus => { 
        :ssl_verifypeer => false,
        :ssl_verifyhost => 0,
        :connecttimeout => 30,
        :timeout => 30
    }
}
HTMLProofer.check_directory(File.join(File.dirname(__FILE__), '../_site'), options).run